from __future__ import annotations

from typing import Protocol
from uuid import UUID

from .entidades import Romaneo


class RepositorioRomaneos(Protocol):
    async def guardar(self, romaneo: Romaneo) -> None: ...

    async def obtener(self, romaneo_id: UUID) -> Romaneo | None: ...

    async def proximo_numero(self) -> int: ...


class LectorBascula(Protocol):
    """Adaptador de hardware. Pendiente §4.4: confirmar si la báscula tiene
    salida digital. Mientras tanto, el adaptador manual cumple el contrato."""

    async def leer_kg(self) -> tuple[str, bool]:
        """Devuelve (kg, es_lectura_estable)."""
        ...
