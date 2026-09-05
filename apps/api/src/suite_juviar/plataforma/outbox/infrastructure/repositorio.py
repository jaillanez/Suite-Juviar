from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from suite_juviar.plataforma.outbox.domain.entidades import EntradaOutbox, EventoDeDominio


class OutboxSQL:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def publicar(self, evento: EventoDeDominio) -> None:
        await self._session.execute(
            text(
                "INSERT INTO plataforma.outbox "
                "(id, nombre, modulo_origen, payload, ocurrido_en, estado, intentos) "
                "VALUES (:id, :n, :m, :p, :ts, 'PENDIENTE', 0)"
            ),
            {
                "id": evento.id,
                "n": evento.nombre,
                "m": evento.modulo_origen,
                "p": json.dumps(evento.payload),
                "ts": evento.ocurrido_en,
            },
        )

    async def tomar_pendientes(self, limite: int = 100) -> list[EntradaOutbox]:
        raise NotImplementedError("Mapeo pendiente de la migración inicial")

    async def confirmar(self, entrada: EntradaOutbox) -> None:
        raise NotImplementedError
