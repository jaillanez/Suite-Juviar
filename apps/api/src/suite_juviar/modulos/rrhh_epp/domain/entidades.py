"""Entrega de EPP y ropa de trabajo (RD 062/11, catálogo RD 068/11).

Regla 3 de construcción: no hay texto libre donde hay catálogo. El operario del
depósito selecciona de una lista; nunca escribe marca ni modelo a mano. Por eso
`ItemEntregado` referencia un código del catálogo y no acepta descripción libre.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class EstadoConstancia(StrEnum):
    BORRADOR = "BORRADOR"
    FIRMADA = "FIRMADA"


@dataclass(frozen=True, slots=True)
class ElementoCatalogo:
    """Una fila del RD 068/11 digitalizado. Ej.: número de orden ``104-B``."""

    codigo: str
    descripcion: str
    marca: str
    modelo: str
    certificacion: str | None
    vida_util_dias: int | None


@dataclass(frozen=True, slots=True)
class ItemEntregado:
    codigo_catalogo: str
    cantidad: int
    talle: str | None = None

    def __post_init__(self) -> None:
        if self.cantidad < 1:
            raise ValueError("La cantidad entregada debe ser al menos 1")


@dataclass(slots=True)
class ConstanciaEntrega:
    """Una vez firmada, no se toca.

    `firmar()` es una transición de un solo sentido y todos los métodos de
    edición verifican el estado. Una entrega mal cargada se anula y se emite
    otra: el papel que vería una inspección no se reescribe.
    """

    legajo: str  # viene de Nexus, no se tipea
    sector: str
    puesto: str
    entregado_por_legajo: str
    fecha: date
    items: list[ItemEntregado] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)
    estado: EstadoConstancia = EstadoConstancia.BORRADOR
    documento_firmado_id: UUID | None = None
    firmada_en: datetime | None = None

    def agregar(self, item: ItemEntregado) -> None:
        if self.estado is EstadoConstancia.FIRMADA:
            raise ValueError("No se modifica una constancia firmada")
        self.items.append(item)

    def firmar(self, documento_firmado_id: UUID) -> None:
        if self.estado is EstadoConstancia.FIRMADA:
            raise ValueError("La constancia ya está firmada")
        if not self.items:
            raise ValueError("No se firma una constancia sin elementos")
        self.estado = EstadoConstancia.FIRMADA
        self.documento_firmado_id = documento_firmado_id
        self.firmada_en = datetime.now(UTC)
