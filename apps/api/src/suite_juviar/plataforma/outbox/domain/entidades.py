"""Eventos de dominio con patrón outbox.

Un módulo nunca importa a otro. Cuando algo tiene que cruzar, publica un evento
en la misma transacción que escribe su propio estado, y un worker lo entrega
con reintentos y backoff. Si el worker se cae, el evento sigue en la tabla.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID, uuid4


class EstadoEvento(StrEnum):
    PENDIENTE = "PENDIENTE"
    PROCESANDO = "PROCESANDO"
    ENTREGADO = "ENTREGADO"
    FALLIDO = "FALLIDO"      # agotó reintentos; requiere intervención humana


@dataclass(frozen=True, slots=True)
class EventoDeDominio:
    nombre: str              # "recepcion.romaneo.cerrado"
    modulo_origen: str
    payload: dict[str, Any]
    id: UUID = field(default_factory=uuid4)
    ocurrido_en: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class EntradaOutbox:
    evento: EventoDeDominio
    estado: EstadoEvento = EstadoEvento.PENDIENTE
    intentos: int = 0
    ultimo_error: str | None = None
    proximo_intento: datetime | None = None

    MAX_INTENTOS: ClassVar[int] = 8

    def marcar_fallo(self, error: str, ahora: datetime) -> None:
        self.intentos += 1
        self.ultimo_error = error[:1000]
        if self.intentos >= self.MAX_INTENTOS:
            self.estado = EstadoEvento.FALLIDO
        else:
            self.estado = EstadoEvento.PENDIENTE
            self.proximo_intento = ahora  # el adaptador aplica el backoff

    def marcar_entregado(self) -> None:
        self.estado = EstadoEvento.ENTREGADO
        self.ultimo_error = None
