"""Ingreso a Gestión con correo y contraseña, y administración de cuentas."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Protocol
from uuid import uuid4

from ..domain.usuarios import (
    DatosDeUsuarioInvalidos,
    IngresoInvalido,
    SesionGuardada,
    Usuario,
    validar_clave,
)

_N, _R, _P = 2**14, 8, 1
EMPRESAS = frozenset({"ENAV", "JUBIAR"})
DURACION_SESION = timedelta(hours=12)
INTENTOS_PERMITIDOS = 5  # por correo y equipo de origen
INTENTOS_POR_ORIGEN = 30  # por equipo de origen, sumando todos los correos
ESPERA_TRAS_BLOQUEO = 15 * 60
MAXIMO_CLAVES_VIGILADAS = 10_000


def cifrar_clave(clave: str) -> str:
    sal = secrets.token_bytes(16)
    resumen = hashlib.scrypt(clave.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${sal.hex()}${resumen.hex()}"


def clave_coincide(clave: str, guardada: str) -> bool:
    try:
        _, n, r, p, sal, resumen = guardada.split("$")
        calculado = hashlib.scrypt(
            clave.encode(), salt=bytes.fromhex(sal), n=int(n), r=int(r), p=int(p), dklen=32,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculado.hex(), resumen)


# Se compara contra esta cuando el correo no existe, para que la respuesta tarde lo mismo.
_CLAVE_FICTICIA = cifrar_clave(secrets.token_urlsafe(16))


class RepositorioUsuarios(Protocol):
    def crear(self, usuario: Usuario, clave_cifrada: str) -> None: ...
    def obtener(self, usuario_id: str) -> Usuario | None: ...
    def obtener_por_email(self, email: str) -> tuple[Usuario, str] | None: ...
    def listar(self) -> list[Usuario]: ...
    def actualizar(self, usuario: Usuario) -> None: ...
    def cambiar_clave(self, usuario_id: str, clave_cifrada: str, debe_cambiar: bool) -> None: ...
    def guardar_sesion(self, token: str, sesion: SesionGuardada) -> None: ...
    def obtener_sesion(self, token: str) -> SesionGuardada | None: ...
    def cambiar_empresa_sesion(self, token: str, empresa: str) -> None: ...
    def borrar_sesion(self, token: str) -> None: ...
    def borrar_sesiones_de(self, usuario_id: str, salvo_token: str | None = None) -> None: ...
    def registrar_evento(self, actor: str, accion: str, detalle: str = "") -> None: ...
    def eventos(self, limite: int = 200) -> list[dict[str, str]]: ...


def _normalizar_email(email: str) -> str:
    email = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise DatosDeUsuarioInvalidos("El correo no es válido.")
    return email


class ServicioIngreso:
    def __init__(self, repositorio: RepositorioUsuarios, perfiles_validos: frozenset[str]):
        self.repositorio = repositorio
        self.perfiles_validos = perfiles_validos
        self._fallos: dict[str, list[float]] = {}
        self._bloqueo_fallos = Lock()

    # --- ingreso -----------------------------------------------------------------
    # Los intentos se cuentan por correo y equipo de origen: alguien de afuera no puede
    # bloquearle la cuenta a otra persona que entra desde su propio equipo.
    def _recientes(self, clave: str, ahora: float) -> int:
        recientes = [t for t in self._fallos.get(clave, []) if ahora - t < ESPERA_TRAS_BLOQUEO]
        if recientes:
            self._fallos[clave] = recientes
        else:
            self._fallos.pop(clave, None)
        return len(recientes)

    def _bloqueado(self, email: str, origen: str) -> bool:
        ahora = time.monotonic()
        with self._bloqueo_fallos:
            return (self._recientes(f"{origen}|{email}", ahora) >= INTENTOS_PERMITIDOS
                    or self._recientes(origen, ahora) >= INTENTOS_POR_ORIGEN)

    def _anotar_fallo(self, email: str, origen: str) -> None:
        ahora = time.monotonic()
        with self._bloqueo_fallos:
            if len(self._fallos) >= MAXIMO_CLAVES_VIGILADAS:
                for clave in list(self._fallos):
                    self._recientes(clave, ahora)
            if len(self._fallos) < MAXIMO_CLAVES_VIGILADAS:
                self._fallos.setdefault(f"{origen}|{email}", []).append(ahora)
            self._fallos.setdefault(origen, []).append(ahora)

    @staticmethod
    def _para_registro(email: str) -> str:
        """Lo escrito en el ingreso va a la bitácora solo si tiene forma de correo."""
        try:
            return _normalizar_email(email)[:120]
        except DatosDeUsuarioInvalidos:
            return "(correo no válido)"

    def ingresar(self, email: str, clave: str, empresa: str | None = None,
                 origen: str = "") -> tuple[str, Usuario]:
        email = email.strip().lower()
        if self._bloqueado(email, origen):
            self.repositorio.registrar_evento(self._para_registro(email), "INGRESO_BLOQUEADO", origen)
            raise IngresoInvalido(
                "Demasiados intentos fallidos. Esperá 15 minutos y volvé a intentar."
            )
        encontrado = self.repositorio.obtener_por_email(email)
        guardada = encontrado[1] if encontrado else _CLAVE_FICTICIA
        valida = clave_coincide(clave, guardada)
        if not encontrado or not valida or not encontrado[0].activo:
            self._anotar_fallo(email, origen)
            self.repositorio.registrar_evento(self._para_registro(email), "INGRESO_FALLIDO", origen)
            raise IngresoInvalido("Correo o contraseña incorrectos.")
        usuario = encontrado[0]
        with self._bloqueo_fallos:
            self._fallos.pop(f"{origen}|{email}", None)
        empresa_sesion = (empresa or "").upper()
        if empresa_sesion not in usuario.empresas:
            empresa_sesion = usuario.empresas[0]
        token = secrets.token_urlsafe(32)
        self.repositorio.guardar_sesion(
            token, SesionGuardada(usuario.id, empresa_sesion, datetime.now(UTC) + DURACION_SESION)
        )
        self.repositorio.registrar_evento(usuario.email, "INGRESO", origen)
        return token, usuario

    def resolver(self, token: str) -> tuple[Usuario, SesionGuardada] | None:
        sesion = self.repositorio.obtener_sesion(token)
        if sesion is None:
            return None
        if sesion.vence <= datetime.now(UTC):
            self.repositorio.borrar_sesion(token)
            return None
        usuario = self.repositorio.obtener(sesion.usuario_id)
        if usuario is None or not usuario.activo:
            self.repositorio.borrar_sesion(token)
            return None
        if sesion.empresa not in usuario.empresas:
            # Le quitaron esa empresa: la sesión sigue sólo en una de las que le quedan.
            sesion = replace(sesion, empresa=usuario.empresas[0])
            self.repositorio.cambiar_empresa_sesion(token, sesion.empresa)
        return usuario, sesion

    def salir(self, token: str) -> None:
        resuelto = self.resolver(token)
        self.repositorio.borrar_sesion(token)
        if resuelto:
            self.repositorio.registrar_evento(resuelto[0].email, "SALIDA")

    def cambiar_empresa(self, token: str, empresa: str) -> None:
        empresa = empresa.upper()
        resuelto = self.resolver(token)
        if resuelto is None:
            raise IngresoInvalido("La sesión venció. Volvé a ingresar.")
        if empresa not in resuelto[0].empresas:
            raise DatosDeUsuarioInvalidos("No tenés acceso a esa empresa.")
        self.repositorio.cambiar_empresa_sesion(token, empresa)

    def cambiar_clave_propia(self, token: str, actual: str, nueva: str) -> None:
        resuelto = self.resolver(token)
        if resuelto is None:
            raise IngresoInvalido("La sesión venció. Volvé a ingresar.")
        usuario = resuelto[0]
        encontrado = self.repositorio.obtener_por_email(usuario.email)
        if encontrado is None or not clave_coincide(actual, encontrado[1]):
            raise DatosDeUsuarioInvalidos("La contraseña actual no es correcta.")
        validar_clave(nueva)
        if nueva == actual:
            raise DatosDeUsuarioInvalidos("La nueva contraseña tiene que ser distinta de la actual.")
        self.repositorio.cambiar_clave(usuario.id, cifrar_clave(nueva), debe_cambiar=False)
        self.repositorio.borrar_sesiones_de(usuario.id, salvo_token=token)
        self.repositorio.registrar_evento(usuario.email, "CAMBIO_CLAVE")

    # --- administración ----------------------------------------------------------
    def _validar_perfil_empresas(self, perfil: str, empresas: list[str] | tuple[str, ...]
                                 ) -> tuple[str, tuple[str, ...]]:
        perfil = perfil.upper()
        if perfil not in self.perfiles_validos:
            raise DatosDeUsuarioInvalidos("Perfil inexistente.")
        elegidas = {e.strip().upper() for e in empresas if e.strip()}
        if not elegidas:
            raise DatosDeUsuarioInvalidos("Elegí al menos una empresa.")
        if not elegidas <= EMPRESAS:
            raise DatosDeUsuarioInvalidos("Empresa inexistente.")
        return perfil, tuple(e for e in ("ENAV", "JUBIAR") if e in elegidas)

    def crear_usuario(self, actor: str, email: str, nombre: str, perfil: str,
                      empresas: list[str] | tuple[str, ...], clave_inicial: str) -> Usuario:
        perfil, elegidas = self._validar_perfil_empresas(perfil, empresas)
        if not nombre.strip():
            raise DatosDeUsuarioInvalidos("El nombre es obligatorio.")
        validar_clave(clave_inicial)
        usuario = Usuario(
            str(uuid4()), _normalizar_email(email), nombre.strip(), perfil, elegidas,
            activo=True, debe_cambiar_clave=True, creado_en=datetime.now(UTC),
        )
        try:
            self.repositorio.crear(usuario, cifrar_clave(clave_inicial))
        except ValueError as exc:
            raise DatosDeUsuarioInvalidos(str(exc)) from exc
        self.repositorio.registrar_evento(actor, "ALTA_USUARIO", f"{usuario.email} ({perfil})")
        return usuario

    def modificar_usuario(self, actor: str, usuario_id: str, *, nombre: str, perfil: str,
                          empresas: list[str] | tuple[str, ...], activo: bool) -> Usuario:
        usuario = self.repositorio.obtener(usuario_id)
        if usuario is None:
            raise LookupError("Usuario inexistente.")
        perfil, elegidas = self._validar_perfil_empresas(perfil, empresas)
        if not nombre.strip():
            raise DatosDeUsuarioInvalidos("El nombre es obligatorio.")
        if usuario.email == actor and (not activo or perfil != usuario.perfil):
            raise DatosDeUsuarioInvalidos("No podés desactivarte ni cambiar tu propio perfil.")
        nuevo = replace(usuario, nombre=nombre.strip(), perfil=perfil, empresas=elegidas, activo=activo)
        self.repositorio.actualizar(nuevo)
        if not activo or perfil != usuario.perfil or not set(elegidas) >= set(usuario.empresas):
            self.repositorio.borrar_sesiones_de(usuario.id)
        self.repositorio.registrar_evento(
            actor, "MODIFICACION_USUARIO",
            f"{usuario.email}: perfil {usuario.perfil}→{perfil}, activo {usuario.activo}→{activo}",
        )
        return nuevo

    def restablecer_clave(self, actor: str, usuario_id: str, clave_temporal: str) -> None:
        usuario = self.repositorio.obtener(usuario_id)
        if usuario is None:
            raise LookupError("Usuario inexistente.")
        validar_clave(clave_temporal)
        self.repositorio.cambiar_clave(usuario.id, cifrar_clave(clave_temporal), debe_cambiar=True)
        self.repositorio.borrar_sesiones_de(usuario.id)
        self.repositorio.registrar_evento(actor, "RESTABLECIMIENTO_CLAVE", usuario.email)
