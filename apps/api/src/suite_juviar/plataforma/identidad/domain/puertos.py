"""Puertos de identidad interna.

Nótese la ausencia deliberada de `guardar`, `crear` y `eliminar`.
Nexus es el dueño del dato; el sistema lo lee y nunca lo escribe.
"""

from __future__ import annotations

from typing import Protocol

from .entidades import Empresa, Legajo, NumeroLegajo


class RepositorioLegajos(Protocol):
    async def obtener(self, numero: NumeroLegajo) -> Legajo | None: ...

    async def buscar_por_dni(self, dni: str) -> Legajo | None: ...

    async def listar_por_sector(
        self, sector: str, empresa: Empresa, solo_activos: bool = True
    ) -> list[Legajo]: ...
