"""Personas que sólo suben facturas desde el celular, con un link personal y un PIN.

No son usuarios de Gestión: entran a una sola pantalla (``/subir``) y su sesión
tiene un único permiso, ``controles_fiscales.subir_celular``.

Un PIN de 3 dígitos son sólo 1000 combinaciones. Por eso cada persona tiene además
un link personal con un código largo al azar (192 bits): sin el link no hay a quién
probarle PINs, y con el link se cortan los intentos a los 5 seguidos (15 minutos) y a
los 20 sin un ingreso bueno (el link queda desactivado hasta que se regenere).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

PERMISO_SUBIDA = "controles_fiscales.subir_celular"
DURACION_SESION_SUBIDA = timedelta(days=30)
FALLOS_PARA_BLOQUEAR = 5
DURACION_BLOQUEO = timedelta(minutes=15)
FALLOS_PARA_DESACTIVAR = 20
DIGITOS_PIN = 3


@dataclass(frozen=True, slots=True)
class PersonaSubida:
    id: str  # identificador público corto: va en el link y en el nombre de quien cargó
    nombre: str
    empresas: tuple[str, ...]
    activo: bool
    creado_por: str
    creado_en: datetime
    fallos_seguidos: int = 0
    fallos_acumulados: int = 0  # desde el último ingreso bueno
    bloqueado_hasta: datetime | None = None
    link_desactivado: bool = False
    ultimo_ingreso: datetime | None = None

    @property
    def actor(self) -> str:
        """Con este nombre quedan cargadas sus facturas (y así se sabe cuáles son suyas)."""
        return f"{self.nombre} (PIN {self.id})"


@dataclass(frozen=True, slots=True)
class SesionSubida:
    persona_id: str
    vence: datetime


class IngresoSubidaInvalido(Exception):
    """PIN o link incorrecto, persona bloqueada o link desactivado."""

    def __init__(self, mensaje: str, motivo: str, intentos_restantes: int | None = None,
                 bloqueado_hasta: datetime | None = None) -> None:
        super().__init__(mensaje)
        self.motivo = motivo  # "link" | "pin" | "bloqueado" | "desactivado" | "demasiados"
        self.intentos_restantes = intentos_restantes
        self.bloqueado_hasta = bloqueado_hasta


class DatosDeSubidaInvalidos(ValueError):
    pass


def validar_pin(pin: str) -> str:
    pin = (pin or "").strip()
    if len(pin) != DIGITOS_PIN or not pin.isdigit() or not pin.isascii():
        raise DatosDeSubidaInvalidos(f"El PIN tiene que ser de {DIGITOS_PIN} números.")
    return pin
