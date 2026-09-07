from __future__ import annotations

from typing import Protocol

from .modelos import Adjunto, PersonaLegajo


class FuenteLegajos(Protocol):
    @property
    def simulada(self) -> bool: ...

    def obtener(self, legajo: str) -> PersonaLegajo | None: ...


class RepositorioAdjuntos(Protocol):
    def guardar(self, adjunto: Adjunto) -> None: ...

    def obtener(self, adjunto_id: str) -> Adjunto | None: ...
