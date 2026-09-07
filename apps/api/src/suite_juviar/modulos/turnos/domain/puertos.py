from __future__ import annotations

from datetime import date
from typing import Protocol

from .entidades import Fichada, Imputacion


class FuenteFichadas(Protocol):
    @property
    def simulada(self) -> bool: ...

    def listar(self, desde: date, hasta: date) -> list[Fichada]: ...


class ExportadorNovedades(Protocol):
    @property
    def simulada(self) -> bool: ...

    def exportar(self, imputaciones: list[Imputacion]) -> str: ...
