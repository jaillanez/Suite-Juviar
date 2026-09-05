from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from suite_juviar.plataforma.bitacora.domain.entidades import AsientoBitacora


class BitacoraSQL:
    """Solo INSERT y SELECT. El rol de aplicación tiene revocados UPDATE y
    DELETE sobre bitacora.asiento, así que la inmutabilidad no depende de que
    esta clase no tenga los métodos: tampoco los permite el motor."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def registrar(self, asiento: AsientoBitacora) -> None:
        await self._session.execute(
            text(
                "INSERT INTO bitacora.asiento "
                "(id, accion, actor_tipo, actor_id, entidad, entidad_id, modulo, datos, ocurrido_en) "
                "VALUES (:id, :accion, :at, :ai, :e, :eid, :m, :datos, :ts)"
            ),
            {
                "id": asiento.id,
                "accion": asiento.accion,
                "at": asiento.actor.tipo.value,
                "ai": asiento.actor.identificador,
                "e": asiento.entidad,
                "eid": asiento.entidad_id,
                "m": asiento.modulo,
                "datos": asiento.datos,
                "ts": asiento.ocurrido_en,
            },
        )

    async def consultar(self, entidad: str, entidad_id: str) -> list[AsientoBitacora]:
        raise NotImplementedError("Mapeo pendiente de la migración inicial")
