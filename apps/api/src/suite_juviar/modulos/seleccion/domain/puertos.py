from __future__ import annotations

from typing import Protocol

from .modelos import CVOriginal, DocumentoEntrante


class FuenteCV(Protocol):
    @property
    def estado(self) -> str: ...

    def listar_nuevos(self) -> list[DocumentoEntrante]: ...


class RepositorioCVOriginales(Protocol):
    def guardar_original(self, original: CVOriginal) -> bool: ...

    def obtener_original(self, id_original: str) -> CVOriginal | None: ...

    def existe_referencia(self, referencia_fuente: str) -> bool: ...

