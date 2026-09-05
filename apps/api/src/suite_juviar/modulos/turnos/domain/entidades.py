"""Turnos rotativos y novedades. Sincronización Time <-> Nexus.

El problema real: los supervisores cambian los turnos rotativos en bodega y no
avisan a administración, y aparecen diferencias de 8 horas entre ausencia y
hora extra. El cambio nace en producción, no en RRHH.

Contrato §5.2: el cambio se carga una sola vez, donde ocurre, con el mínimo
posible de datos —legajo saliente, legajo entrante, fecha y horario— y viaja
hacia Time y Nexus.
"""

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
    """Lo que carga el supervisor en la pantalla ultra simple de bodega."""

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
    """Lo que hoy se audita en un Excel. El objetivo de la etapa 1 es que este
    Excel deje de existir, no que conviva con el sistema (§6.4)."""

    legajo: str
    fecha: date
    minutos_planificados: int
    minutos_marcados: int
    justificado_por_cambio: UUID | None = None
    sincronizacion: EstadoSincronizacion = EstadoSincronizacion.PENDIENTE

    @property
    def minutos_desvio(self) -> int:
        return self.minutos_marcados - self.minutos_planificados
