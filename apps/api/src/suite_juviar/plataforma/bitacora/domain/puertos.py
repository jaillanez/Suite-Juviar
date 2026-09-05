from __future__ import annotations

from typing import Protocol

from .entidades import AsientoBitacora


class Bitacora(Protocol):
    """Solo se agrega y se consulta. No existe modificar ni borrar."""

    async def registrar(self, asiento: AsientoBitacora) -> None: ...

    async def consultar(
        self, entidad: str, entidad_id: str
    ) -> list[AsientoBitacora]: ...
