from __future__ import annotations

from typing import Protocol

from .entidades import EntradaOutbox, EventoDeDominio


class Outbox(Protocol):
    async def publicar(self, evento: EventoDeDominio) -> None:
        """Se llama dentro de la misma transacción que el cambio de estado."""
        ...

    async def tomar_pendientes(self, limite: int = 100) -> list[EntradaOutbox]: ...

    async def confirmar(self, entrada: EntradaOutbox) -> None: ...
