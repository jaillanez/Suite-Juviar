from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Protocol

from .modelos import MovimientoEPP


class FuenteEntregas(Protocol):
    @property
    def simulada(self) -> bool: ...

    def listar(self, desde: date, hasta: date) -> list[MovimientoEPP]: ...


class PrecioItem(Protocol):
    @property
    def dueno_dato(self) -> str: ...

    @property
    def simulada(self) -> bool: ...

    def obtener(self, item_codigo: str, fecha: date) -> Decimal | None: ...
