"""Cosecha y personal temporario.

Contrato §5.4: el temporario entra por el mismo maestro de legajos de Nexus,
con una marca de tipo de vínculo. No se maneja en una planilla aparte. Este
módulo no guarda personas: arma el lote de alta y lo empuja hacia Nexus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class EstadoLote(StrEnum):
    PREPARADO = "PREPARADO"
    ENVIADO = "ENVIADO"
    CONFIRMADO = "CONFIRMADO"
    CON_ERRORES = "CON_ERRORES"


@dataclass(frozen=True, slots=True)
class SolicitudAlta:
    dni: str
    nombre: str
    apellido: str
    sector: str
    puesto: str
    empresa: str
    desde: date
    hasta: date


@dataclass(slots=True)
class LoteAltaMasiva:
    """Alta estacional. Cada persona dada de alta necesita EPP igual que el
    permanente: el evento de confirmación lo consume el módulo de EPP."""

    temporada: str                    # "vendimia-2027"
    solicitudes: list[SolicitudAlta]
    solicitado_por_legajo: str
    id: UUID = field(default_factory=uuid4)
    estado: EstadoLote = EstadoLote.PREPARADO
    creado_en: datetime = field(default_factory=lambda: datetime.now(UTC))
    errores: list[str] = field(default_factory=list)
