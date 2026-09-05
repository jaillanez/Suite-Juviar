from __future__ import annotations

from typing import Protocol

from .entidades import ConstanciaEntrega, ElementoCatalogo


class CatalogoEPP(Protocol):
    async def obtener(self, codigo: str) -> ElementoCatalogo | None: ...

    async def listar_por_puesto(self, puesto: str, sector: str) -> list[ElementoCatalogo]:
        """Matriz Puesto vs. EPP, provista por Higiene y Seguridad (§7.2)."""
        ...


class RepositorioConstancias(Protocol):
    async def guardar(self, constancia: ConstanciaEntrega) -> None: ...

    async def historial_por_legajo(self, legajo: str) -> list[ConstanciaEntrega]: ...
