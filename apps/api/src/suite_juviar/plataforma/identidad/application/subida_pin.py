"""Ingreso con link personal + PIN para subir facturas desde el celular, y su administración.

El código del link es ``<id>.<secreto>``: el id es público (también va en el nombre de
quien cargó la factura) y el secreto son 192 bits al azar. Del secreto y del PIN sólo se
guarda el resumen scrypt con sal, igual que las contraseñas de Gestión; las sesiones se
guardan por el SHA-256 del token. Los intentos se cuentan en el servidor.
"""

from __future__ import annotations

import re
import secrets
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from threading import Lock
from typing import Protocol

from ..domain.subida_pin import (
    DURACION_BLOQUEO,
    DURACION_SESION_SUBIDA,
    FALLOS_PARA_BLOQUEAR,
    FALLOS_PARA_DESACTIVAR,
    DatosDeSubidaInvalidos,
    IngresoSubidaInvalido,
    PersonaSubida,
    SesionSubida,
    validar_pin,
)
from .ingreso import EMPRESAS, cifrar_clave, clave_coincide

HORA_ARGENTINA = timezone(timedelta(hours=-3))
# Links con código equivocado desde un mismo equipo antes de frenarlo un rato.
LINKS_INVALIDOS_POR_ORIGEN = 30
ESPERA_LINKS_INVALIDOS = 15 * 60
MAXIMO_ORIGENES_VIGILADOS = 10_000
_ID = re.compile(r"[0-9a-f]{8}")

# Se compara contra estos cuando el link no existe, para que la respuesta tarde lo mismo.
_SECRETO_FICTICIO = cifrar_clave(secrets.token_urlsafe(24))
_PIN_FICTICIO = cifrar_clave("000")

LINK_INVALIDO = "Este link no sirve para entrar. Pedile uno nuevo a Administración."
LINK_DESACTIVADO = ("Este link quedó desactivado por muchos intentos con PIN incorrecto. "
                    "Pedile uno nuevo a Administración.")


def _ahora() -> datetime:
    return datetime.now(UTC)


def _hora(momento: datetime) -> str:
    return momento.astimezone(HORA_ARGENTINA).strftime("%H:%M")


class RepositorioSubida(Protocol):
    def crear(self, persona: PersonaSubida, pin_cifrado: str, secreto_cifrado: str) -> None: ...
    def obtener(self, persona_id: str) -> tuple[PersonaSubida, str, str] | None: ...
    def listar(self) -> list[PersonaSubida]: ...
    def actualizar(self, persona: PersonaSubida) -> None: ...
    def cambiar_pin(self, persona_id: str, pin_cifrado: str) -> None: ...
    def cambiar_secreto(self, persona_id: str, secreto_cifrado: str) -> None: ...
    def guardar_sesion(self, token: str, sesion: SesionSubida) -> None: ...
    def obtener_sesion(self, token: str) -> SesionSubida | None: ...
    def borrar_sesion(self, token: str) -> None: ...
    def borrar_sesiones_de(self, persona_id: str) -> None: ...
    def registrar_evento(self, actor: str, accion: str, detalle: str = "") -> None: ...
    def eventos(self, limite: int = 200) -> list[dict[str, str]]: ...


class ServicioSubidaPin:
    def __init__(self, repositorio: RepositorioSubida, reloj=_ahora) -> None:
        self.repositorio = repositorio
        self._reloj = reloj
        self._bloqueo = Lock()
        self._links_invalidos: dict[str, list[float]] = {}

    # --- administración ------------------------------------------------------
    @staticmethod
    def _empresas(empresas: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        elegidas = {e.strip().upper() for e in empresas if e.strip()}
        if not elegidas:
            raise DatosDeSubidaInvalidos("Elegí al menos una empresa.")
        if not elegidas <= EMPRESAS:
            raise DatosDeSubidaInvalidos("Empresa inexistente.")
        return tuple(e for e in ("ENAV", "JUBIAR") if e in elegidas)

    @staticmethod
    def _pin(pin: str | None) -> str:
        return validar_pin(pin) if pin else f"{secrets.randbelow(1000):03d}"

    def _persona(self, persona_id: str) -> PersonaSubida:
        encontrado = self.repositorio.obtener(persona_id)
        if encontrado is None:
            raise LookupError("No existe esa persona.")
        return encontrado[0]

    def alta(self, actor: str, nombre: str, empresas: list[str] | tuple[str, ...],
             pin: str | None = None) -> tuple[PersonaSubida, str, str]:
        """Devuelve (persona, PIN, código del link): el PIN y el código se muestran una sola vez."""
        nombre = " ".join((nombre or "").split())
        if not nombre:
            raise DatosDeSubidaInvalidos("El nombre es obligatorio.")
        if len(nombre) > 80:
            raise DatosDeSubidaInvalidos("El nombre es muy largo.")
        elegidas = self._empresas(empresas)
        pin = self._pin(pin)
        persona_id = secrets.token_hex(4)
        while self.repositorio.obtener(persona_id) is not None:
            persona_id = secrets.token_hex(4)
        secreto = secrets.token_urlsafe(24)
        persona = PersonaSubida(persona_id, nombre, elegidas, True, actor, self._reloj())
        self.repositorio.crear(persona, cifrar_clave(pin), cifrar_clave(secreto))
        self.repositorio.registrar_evento(actor, "ALTA_SUBIDA_PIN", f"{persona.actor} ({','.join(elegidas)})")
        return persona, pin, f"{persona_id}.{secreto}"

    def regenerar_pin(self, actor: str, persona_id: str, pin: str | None = None) -> tuple[PersonaSubida, str]:
        with self._bloqueo:
            persona = self._persona(persona_id)
            pin = self._pin(pin)
            self.repositorio.cambiar_pin(persona.id, cifrar_clave(pin))
            persona = replace(persona, fallos_seguidos=0, bloqueado_hasta=None)
            self.repositorio.actualizar(persona)
            self.repositorio.borrar_sesiones_de(persona.id)
        self.repositorio.registrar_evento(actor, "REGENERAR_PIN_SUBIDA", persona.actor)
        return persona, pin

    def regenerar_link(self, actor: str, persona_id: str) -> tuple[PersonaSubida, str]:
        """El link anterior deja de servir; el nuevo vuelve a habilitar los intentos."""
        with self._bloqueo:
            persona = self._persona(persona_id)
            secreto = secrets.token_urlsafe(24)
            self.repositorio.cambiar_secreto(persona.id, cifrar_clave(secreto))
            persona = replace(persona, fallos_seguidos=0, fallos_acumulados=0, bloqueado_hasta=None,
                              link_desactivado=False)
            self.repositorio.actualizar(persona)
            self.repositorio.borrar_sesiones_de(persona.id)
        self.repositorio.registrar_evento(actor, "REGENERAR_LINK_SUBIDA", persona.actor)
        return persona, f"{persona.id}.{secreto}"

    def desactivar(self, actor: str, persona_id: str) -> PersonaSubida:
        with self._bloqueo:
            persona = replace(self._persona(persona_id), activo=False)
            self.repositorio.actualizar(persona)
            self.repositorio.borrar_sesiones_de(persona.id)
        self.repositorio.registrar_evento(actor, "DESACTIVAR_SUBIDA_PIN", persona.actor)
        return persona

    def listar(self) -> list[PersonaSubida]:
        return self.repositorio.listar()

    def estado(self, persona: PersonaSubida) -> str:
        if not persona.activo:
            return "inactivo"
        if persona.link_desactivado:
            return "link_desactivado"
        if persona.bloqueado_hasta is not None and persona.bloqueado_hasta > self._reloj():
            return "bloqueado"
        return "activo"

    def vista(self, persona: PersonaSubida) -> dict[str, object]:
        """Lo que ve Administración: nunca el PIN ni el link (se muestran una sola vez, al generarlos)."""
        estado = self.estado(persona)
        return {
            "id": persona.id, "nombre": persona.nombre, "actor": persona.actor, "empresas": list(persona.empresas),
            "activo": persona.activo, "estado": estado,
            "bloqueado_hasta": persona.bloqueado_hasta if estado == "bloqueado" else None,
            "fallos_acumulados": persona.fallos_acumulados, "ultimo_ingreso": persona.ultimo_ingreso,
            "creado_por": persona.creado_por, "creado_en": persona.creado_en,
        }

    # --- ingreso ---------------------------------------------------------------
    def _origen_frenado(self, origen: str) -> bool:
        ahora = time.monotonic()
        recientes = [t for t in self._links_invalidos.get(origen, []) if ahora - t < ESPERA_LINKS_INVALIDOS]
        if recientes:
            self._links_invalidos[origen] = recientes
        else:
            self._links_invalidos.pop(origen, None)
        return len(recientes) >= LINKS_INVALIDOS_POR_ORIGEN

    def _anotar_link_invalido(self, origen: str) -> None:
        if len(self._links_invalidos) >= MAXIMO_ORIGENES_VIGILADOS:
            for otro in list(self._links_invalidos):
                self._origen_frenado(otro)
        if len(self._links_invalidos) < MAXIMO_ORIGENES_VIGILADOS or origen in self._links_invalidos:
            self._links_invalidos.setdefault(origen, []).append(time.monotonic())

    def ingresar(self, codigo: str, pin: str, origen: str = "") -> tuple[str, PersonaSubida]:
        persona_id, _, secreto = (codigo or "").strip().partition(".")
        with self._bloqueo:
            if self._origen_frenado(origen):
                raise IngresoSubidaInvalido(
                    "Demasiados intentos desde este equipo. Esperá 15 minutos.", "demasiados")
            encontrado = self.repositorio.obtener(persona_id) if _ID.fullmatch(persona_id) else None
            # Siempre se calculan los dos resúmenes: tarda lo mismo exista o no el link.
            secreto_ok = clave_coincide(secreto, encontrado[2] if encontrado else _SECRETO_FICTICIO)
            pin_ok = clave_coincide(pin, encontrado[1] if encontrado else _PIN_FICTICIO)
            if encontrado is None or not secreto_ok or not encontrado[0].activo:
                self._anotar_link_invalido(origen)
                self.repositorio.registrar_evento("(link de subida)", "INGRESO_SUBIDA_LINK_INVALIDO", origen)
                raise IngresoSubidaInvalido(LINK_INVALIDO, "link")
            persona = encontrado[0]
            ahora = self._reloj()
            # A partir de acá quien escribe tiene el link verdadero: se le puede decir qué pasa.
            if persona.link_desactivado:
                raise IngresoSubidaInvalido(LINK_DESACTIVADO, "desactivado")
            if persona.bloqueado_hasta is not None and persona.bloqueado_hasta > ahora:
                raise IngresoSubidaInvalido(
                    f"Bloqueado por muchos PIN incorrectos hasta las {_hora(persona.bloqueado_hasta)}.",
                    "bloqueado", bloqueado_hasta=persona.bloqueado_hasta)
            if not pin_ok:
                self._fallo(persona, ahora, origen)
            persona = replace(persona, fallos_seguidos=0, fallos_acumulados=0, bloqueado_hasta=None,
                              ultimo_ingreso=ahora)
            self.repositorio.actualizar(persona)
            token = secrets.token_urlsafe(32)
            self.repositorio.guardar_sesion(token, SesionSubida(persona.id, ahora + DURACION_SESION_SUBIDA))
        self.repositorio.registrar_evento(persona.actor, "INGRESO_SUBIDA", origen)
        return token, persona

    def _fallo(self, persona: PersonaSubida, ahora: datetime, origen: str) -> None:
        seguidos, acumulados = persona.fallos_seguidos + 1, persona.fallos_acumulados + 1
        self.repositorio.registrar_evento(persona.actor, "INGRESO_SUBIDA_FALLIDO", origen)
        if acumulados >= FALLOS_PARA_DESACTIVAR:
            self.repositorio.actualizar(replace(persona, fallos_seguidos=0, fallos_acumulados=acumulados,
                                                bloqueado_hasta=None, link_desactivado=True))
            self.repositorio.registrar_evento(persona.actor, "LINK_SUBIDA_DESACTIVADO",
                                              f"{acumulados} PIN incorrectos")
            raise IngresoSubidaInvalido(LINK_DESACTIVADO, "desactivado")
        if seguidos >= FALLOS_PARA_BLOQUEAR:
            hasta = ahora + DURACION_BLOQUEO
            self.repositorio.actualizar(replace(persona, fallos_seguidos=0, fallos_acumulados=acumulados,
                                                bloqueado_hasta=hasta))
            self.repositorio.registrar_evento(persona.actor, "BLOQUEO_SUBIDA", f"hasta {hasta.isoformat()}")
            raise IngresoSubidaInvalido(
                f"PIN incorrecto. Quedó bloqueado por 15 minutos, hasta las {_hora(hasta)}.",
                "bloqueado", bloqueado_hasta=hasta)
        self.repositorio.actualizar(replace(persona, fallos_seguidos=seguidos, fallos_acumulados=acumulados))
        restantes = FALLOS_PARA_BLOQUEAR - seguidos
        raise IngresoSubidaInvalido(
            f"PIN incorrecto. Te {'queda 1 intento' if restantes == 1 else f'quedan {restantes} intentos'}.",
            "pin", intentos_restantes=restantes)

    def resolver(self, token: str) -> PersonaSubida | None:
        sesion = self.repositorio.obtener_sesion(token)
        if sesion is None:
            return None
        if sesion.vence <= self._reloj():
            self.repositorio.borrar_sesion(token)
            return None
        encontrado = self.repositorio.obtener(sesion.persona_id)
        if encontrado is None or not encontrado[0].activo:
            self.repositorio.borrar_sesion(token)
            return None
        return encontrado[0]

    def salir(self, token: str) -> None:
        persona = self.resolver(token)
        self.repositorio.borrar_sesion(token)
        if persona is not None:
            self.repositorio.registrar_evento(persona.actor, "SALIDA_SUBIDA")
