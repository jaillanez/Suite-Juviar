"""Persistencia de romaneos. Placeholder de mapeo: las tablas se definen en la
migración inicial de Alembic (schema `recepcion`)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from suite_juviar.modulos.recepcion.domain.entidades import Romaneo


class RepositorioRomaneosSQL:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def guardar(self, romaneo: Romaneo) -> None:
        raise NotImplementedError("Mapeo pendiente de la migración inicial")

    async def obtener(self, romaneo_id: UUID) -> Romaneo | None:
        raise NotImplementedError

    async def proximo_numero(self) -> int:
        raise NotImplementedError
