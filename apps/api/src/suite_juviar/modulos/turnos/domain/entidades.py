"""Modelo de cronogramas versionados, conciliación y propuestas de Turnos."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from enum import StrEnum
from uuid import UUID, uuid4


class EstadoSincronizacion(StrEnum):
    PENDIENTE = "PENDIENTE"
    SINCRONIZADO = "SINCRONIZADO"
    RECHAZADO = "RECHAZADO"


@dataclass(frozen=True, slots=True)
class CambioDeTurno:
    legajo_saliente: str
    legajo_entrante: str
    fecha: date
    desde: time
    hasta: time
    reportado_por_legajo: str
    id: UUID = field(default_factory=uuid4)
    reportado_en: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.legajo_saliente == self.legajo_entrante:
            raise ValueError("El saliente y el entrante no pueden ser el mismo legajo")


@dataclass(slots=True)
class Desvio:
    legajo: str
    fecha: date
    minutos_planificados: int
    minutos_marcados: int
    justificado_por_cambio: UUID | None = None
    sincronizacion: EstadoSincronizacion = EstadoSincronizacion.PENDIENTE

    @property
    def minutos_desvio(self) -> int:
        return self.minutos_marcados - self.minutos_planificados


class EstadoImputacion(StrEnum):
    PROPUESTA = "PROPUESTA"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"


class EstadoDia(StrEnum):
    PLANIFICADO = "PLANIFICADO"
    REGULARIZADO_TARDE = "REGULARIZADO_TARDE"
    SIN_INFORMAR = "SIN_INFORMAR"


@dataclass(frozen=True, slots=True)
class Cronograma:
    id: UUID
    legajo: str
    sector: str
    fecha: date
    desde: time
    hasta: time
    autor: str
    conocido_en: datetime = field(default_factory=lambda: datetime.now(UTC))
    reemplaza_id: UUID | None = None
    cambio_tardio: bool = False


@dataclass(frozen=True, slots=True)
class CambioCronograma:
    id: UUID
    cronograma_id: UUID
    legajo: str
    sector: str
    fecha_afectada: date
    desde_anterior: time
    hasta_anterior: time
    desde_nuevo: time
    hasta_nuevo: time
    autor: str
    conocido_en: datetime
    tardio: bool


@dataclass(frozen=True, slots=True)
class Fichada:
    legajo: str
    momento: datetime
    tipo: str
    simulada: bool = True


@dataclass(slots=True)
class Imputacion:
    id: UUID
    legajo: str
    fecha: date
    motivo_propuesto: str
    minutos_desvio: int
    estado: EstadoImputacion = EstadoImputacion.PROPUESTA
    aprobada_por: str | None = None
    resuelta_en: datetime | None = None
    motivo_final: str | None = None
    sector: str = ""
    creada_en: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class DiaConciliado:
    legajo: str
    sector: str
    fecha: date
    desde_plan: time
    hasta_plan: time
    primera_marca: datetime | None
    ultima_marca: datetime | None
    minutos_planificados: int
    minutos_marcados: int
    minutos_desvio: int
    tipo_desvio: str | None
    estado_dia: EstadoDia
    propuesta_id: UUID | None


@dataclass(frozen=True, slots=True)
class SalidaBandeja:
    id: UUID
    creada_en: datetime
    estado: str
    formato: str
    archivo: str
    cantidad_dias: int
    personas: tuple[str, ...]
    simulada: bool = True


class FuenteSimuladaEnProduccion(Exception):
    pass
