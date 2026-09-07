from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

MARCA_SIMULADA = "DATOS SIMULADOS — SIN VALIDEZ"


@dataclass(frozen=True, slots=True)
class MovimientoEPP:
    entrega_id: str
    fecha: date
    legajo: str
    sector: str
    puesto: str
    elemento_codigo: str
    item_codigo: str
    cantidad: int
    reclamo_calidad: str | None = None


@dataclass(frozen=True, slots=True)
class MetricasItem:
    item_codigo: str
    sector: str
    puesto: str
    consumo: int
    reclamos: dict[str, int]
    muestra_duracion: int
    duracion_promedio_dias: float | None
    estado_duracion: str


@dataclass(frozen=True, slots=True)
class CostoPersona:
    legajo: str
    costo: Decimal | None
    faltante: str | None


class ExportacionNoPermitida(Exception):
    pass


class ComparacionInvalida(Exception):
    pass


class FuenteSimuladaEnProduccion(Exception):
    pass
