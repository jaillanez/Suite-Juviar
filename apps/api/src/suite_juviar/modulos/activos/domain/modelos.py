from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

_PREFIJO = re.compile(r"^[A-Z]{2,5}$")

# El grupo es uno solo; lo que importa es en qué bodega está cada equipo.
BODEGAS = {"chimbas": "Chimbas", "media-agua": "Media Agua", "lavalle": "Lavalle"}
# A qué empresa del grupo se imputa la factura de una reparación.
EMPRESAS = ("ENAV", "JUBIAR")


def _obligatorio(nombre: str, valor: str | None) -> None:
    if not valor or not valor.strip():
        raise ValueError(f"{nombre} no puede estar vacío.")


@dataclass(frozen=True, slots=True)
class TipoActivo:
    """Clase de bien que se etiqueta: bombas, maquinarias, muebles…"""

    id: str
    nombre: str
    prefijo: str

    def __post_init__(self) -> None:
        _obligatorio("El nombre del tipo", self.nombre)
        if not _PREFIJO.match(self.prefijo):
            raise ValueError("El prefijo del código debe tener de 2 a 5 letras, sin números ni espacios.")


@dataclass(frozen=True, slots=True)
class Sector:
    id: str
    nombre: str
    bodega: str

    def __post_init__(self) -> None:
        _obligatorio("El nombre del sector", self.nombre)
        if self.bodega not in BODEGAS:
            raise ValueError("Elegí la bodega: Chimbas, Media Agua o Lavalle.")


class EstadoActivo(StrEnum):
    EN_PLANTA = "EN_PLANTA"
    EN_TALLER = "EN_TALLER"
    DE_BAJA = "DE_BAJA"


@dataclass(frozen=True, slots=True)
class Activo:
    codigo: str
    tipo_id: str
    descripcion: str
    sector_id: str
    marca: str = ""
    modelo: str = ""
    numero_serie: str = ""
    estado: EstadoActivo = EstadoActivo.EN_PLANTA
    alta_en: datetime | None = None
    alta_por: str = ""
    baja_motivo: str = ""
    baja_en: datetime | None = None
    baja_por: str = ""

    def __post_init__(self) -> None:
        _obligatorio("El código", self.codigo)
        _obligatorio("La descripción", self.descripcion)
        _obligatorio("El sector", self.sector_id)


class TipoMovimiento(StrEnum):
    ALTA = "ALTA"
    TRASLADO = "TRASLADO"
    SALIDA_TALLER = "SALIDA_TALLER"
    REGRESO_TALLER = "REGRESO_TALLER"
    BAJA = "BAJA"


@dataclass(frozen=True, slots=True)
class Movimiento:
    codigo: str
    tipo: TipoMovimiento
    fecha: datetime
    actor: str
    desde_sector_id: str | None = None
    hacia_sector_id: str | None = None
    detalle: str = ""


@dataclass(frozen=True, slots=True)
class Reparacion:
    """Una salida a taller externo; queda abierta hasta que el equipo vuelve."""

    id: str
    codigo: str
    taller: str
    motivo: str
    salida_en: datetime
    salida_por: str
    regreso_en: datetime | None = None
    regreso_por: str | None = None
    costo: float | None = None
    trabajo_realizado: str = ""
    empresa: str | None = None  # a quién va la factura; se carga al volver del taller

    def __post_init__(self) -> None:
        _obligatorio("El taller", self.taller)
        if self.empresa is not None and self.empresa not in EMPRESAS:
            raise ValueError("Elegí a qué empresa va la factura: ENAV o Juviar.")
        _obligatorio("El motivo", self.motivo)
        if self.costo is not None and self.costo < 0:
            raise ValueError("El costo no puede ser negativo.")

    @property
    def abierta(self) -> bool:
        return self.regreso_en is None
