from __future__ import annotations

from typing import Any, Protocol

from .entidades import Parametro


class RepositorioParametros(Protocol):
    async def obtener(self, clave: str) -> Parametro: ...

    async def valor(self, clave: str) -> Any: ...

    async def listar_por_modulo(self, modulo: str) -> list[Parametro]: ...

    async def actualizar(self, clave: str, valor: Any, actor: str) -> Parametro:
        """Solo desde el panel. Deja bitácora del cambio."""
        ...
