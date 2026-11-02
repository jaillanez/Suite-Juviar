from __future__ import annotations

from collections.abc import MutableMapping
from typing import Protocol

from .modelos import Activo, Movimiento, Reparacion, Sector, TipoActivo


class RepositorioActivos(Protocol):
    tipos: MutableMapping[str, TipoActivo]
    sectores: MutableMapping[str, Sector]
    activos: MutableMapping[str, Activo]
    reparaciones: MutableMapping[str, Reparacion]

    def registrar_movimiento(self, movimiento: Movimiento) -> None: ...

    def movimientos(self) -> list[Movimiento]: ...


class Impresora(Protocol):
    def enviar(self, zpl: str) -> None: ...
