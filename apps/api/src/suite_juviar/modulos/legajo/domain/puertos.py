from __future__ import annotations

from typing import Protocol

from .modelos import Adjunto, PersonaLegajo


class FuenteLegajos(Protocol):
    @property
    def simulada(self) -> bool: ...

    def obtener(self, legajo: str) -> PersonaLegajo | None: ...

    def buscar(
        self, *, apellido: str | None = None, legajo: str | None = None,
        sector: str | None = None, empresa: str | None = None,
    ) -> list[PersonaLegajo]: ...


class RepositorioAdjuntos(Protocol):
    def guardar(self, adjunto: Adjunto) -> None: ...

    def obtener(self, adjunto_id: str) -> Adjunto | None: ...

    def listar(self, legajo: str, incluir_bajas: bool = True) -> list[Adjunto]: ...

    def reemplazar(self, adjunto: Adjunto) -> None: ...
