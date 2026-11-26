"""«¿Olvidaste tu contraseña?»: enlace por correo para elegir una contraseña nueva.

El pedido siempre contesta lo mismo y tarda lo mismo, exista o no el correo: lo único que
se hace en el momento es contar el pedido; buscar la cuenta, crear el enlace y mandar el
correo (que puede tardar varios segundos) pasa en segundo plano.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from ..domain.recuperacion import (
    ASUNTO_CORREO,
    PEDIDOS_POR_CORREO,
    PEDIDOS_POR_ORIGEN,
    VENTANA_PEDIDOS,
    VIGENCIA_ENLACE,
    EnlaceDeRecuperacionInvalido,
    cuerpo_correo,
)
from ..domain.usuarios import validar_clave
from .ingreso import RepositorioUsuarios, cifrar_clave

registro = logging.getLogger(__name__)

# (destino, asunto, cuerpo) → False si no hay casilla configurada para mandar.
EnviarCorreo = Callable[[str, str, str], bool]
_FORMA_CORREO = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class RepositorioRecuperacion(Protocol):
    def anotar_pedido_si_hay_cupo(self, email: str, origen: str, ahora: datetime, ventana: timedelta,
                                  por_correo: int, por_origen: int) -> bool: ...
    def reemplazar_enlace(self, usuario_id: str, token_sha256: str, vence: datetime,
                          ahora: datetime) -> None: ...
    def vigente(self, token_sha256: str, ahora: datetime) -> str | None: ...
    def consumir(self, token_sha256: str, ahora: datetime) -> str | None: ...
    def anular_enlaces_de(self, usuario_id: str) -> None: ...


def _resumen(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _en_segundo_plano(tarea: Callable[[], None]) -> None:
    threading.Thread(target=tarea, name="recuperar-clave", daemon=True).start()


class ServicioRecuperacion:
    def __init__(
        self,
        usuarios: RepositorioUsuarios,
        enlaces: RepositorioRecuperacion,
        enviar: EnviarCorreo,
        url_publica: str,
        reloj: Callable[[], datetime] = lambda: datetime.now(UTC),
        ejecutar: Callable[[Callable[[], None]], None] = _en_segundo_plano,
    ) -> None:
        self.usuarios = usuarios
        self.enlaces = enlaces
        self.enviar = enviar
        self.url_publica = url_publica.rstrip("/")
        self.reloj = reloj
        self.ejecutar = ejecutar

    def pedir(self, email: str, origen: str = "") -> None:
        """No devuelve nada ni falla: la respuesta al usuario es siempre la misma."""
        email = (email or "").strip().lower()[:200]
        if not _FORMA_CORREO.fullmatch(email):
            return
        if not self.enlaces.anotar_pedido_si_hay_cupo(
            email, origen, self.reloj(), VENTANA_PEDIDOS, PEDIDOS_POR_CORREO, PEDIDOS_POR_ORIGEN
        ):
            self.usuarios.registrar_evento(email[:120], "RECUPERACION_LIMITE", origen)
            return
        self.ejecutar(lambda: self._procesar(email, origen))

    def _procesar(self, email: str, origen: str) -> None:
        try:
            encontrado = self.usuarios.obtener_por_email(email)
            if encontrado is None or not encontrado[0].activo:
                self.usuarios.registrar_evento(email[:120], "RECUPERACION_SIN_CUENTA", origen)
                return
            usuario = encontrado[0]
            token = secrets.token_urlsafe(32)  # 256 bits
            ahora = self.reloj()
            self.enlaces.reemplazar_enlace(usuario.id, _resumen(token), ahora + VIGENCIA_ENLACE, ahora)
            enlace = f"{self.url_publica}/restablecer/#{token}"
            try:
                enviado = self.enviar(usuario.email, ASUNTO_CORREO, cuerpo_correo(enlace))
            except Exception as exc:  # noqa: BLE001 - el usuario no se entera; queda para Sistemas
                self.enlaces.anular_enlaces_de(usuario.id)
                registro.exception("No se pudo mandar el correo para recuperar la contraseña")
                self.usuarios.registrar_evento(
                    usuario.email, "RECUPERACION_ERROR_ENVIO", f"{type(exc).__name__}: {exc}"[:200])
                return
            if not enviado:
                self.enlaces.anular_enlaces_de(usuario.id)
                registro.error("Recuperar contraseña: no hay casilla de RRHH configurada en Parámetros")
                self.usuarios.registrar_evento(
                    usuario.email, "RECUPERACION_ERROR_ENVIO", "No hay casilla de RRHH configurada en Parámetros.")
                return
            self.usuarios.registrar_evento(usuario.email, "RECUPERACION_ENVIADA", origen)
        except Exception:  # noqa: BLE001 - corre en segundo plano: que no se pierda en silencio
            registro.exception("Falló el pedido para recuperar la contraseña")

    def restablecer(self, token: str, nueva: str, origen: str = "") -> None:
        token = (token or "").strip()
        resumen = _resumen(token)
        if not token or self.enlaces.vigente(resumen, self.reloj()) is None:
            raise EnlaceDeRecuperacionInvalido(
                "El enlace ya se usó o venció. Pedí uno nuevo desde «¿Olvidaste tu contraseña?».")
        # Con una contraseña que no cumple las reglas el enlace sigue sirviendo para reintentar.
        validar_clave(nueva)
        usuario_id = self.enlaces.consumir(resumen, self.reloj())
        usuario = self.usuarios.obtener(usuario_id) if usuario_id else None
        if usuario is None or not usuario.activo:
            raise EnlaceDeRecuperacionInvalido(
                "El enlace ya se usó o venció. Pedí uno nuevo desde «¿Olvidaste tu contraseña?».")
        self.usuarios.cambiar_clave(usuario.id, cifrar_clave(nueva), debe_cambiar=False)
        self.usuarios.borrar_sesiones_de(usuario.id)
        self.enlaces.anular_enlaces_de(usuario.id)
        self.usuarios.registrar_evento(usuario.email, "RECUPERACION_CLAVE_CAMBIADA", origen)
