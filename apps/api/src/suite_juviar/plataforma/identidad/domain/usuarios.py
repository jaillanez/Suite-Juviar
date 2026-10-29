"""Usuarios de Gestión: quién entra, con qué perfil y para qué empresa.

No son empleados (eso es Nexus): son cuentas de acceso a la aplicación interna.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

CLAVE_MINIMA = 10


@dataclass(frozen=True, slots=True)
class Usuario:
    id: str
    email: str
    nombre: str
    perfil: str
    empresa: str
    activo: bool
    debe_cambiar_clave: bool
    creado_en: datetime


@dataclass(frozen=True, slots=True)
class SesionGuardada:
    usuario_id: str
    empresa: str
    vence: datetime


class IngresoInvalido(Exception):
    """Correo o contraseña incorrectos, usuario inactivo o demasiados intentos."""


class DatosDeUsuarioInvalidos(ValueError):
    pass


def validar_clave(clave: str) -> None:
    if len(clave) < CLAVE_MINIMA:
        raise DatosDeUsuarioInvalidos(
            f"La contraseña debe tener al menos {CLAVE_MINIMA} caracteres."
        )
    if clave.strip() != clave or not clave.strip():
        raise DatosDeUsuarioInvalidos("La contraseña no puede empezar ni terminar con espacios.")
