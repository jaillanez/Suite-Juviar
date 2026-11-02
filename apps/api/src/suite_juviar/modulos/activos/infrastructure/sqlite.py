from __future__ import annotations

from pathlib import Path

from suite_juviar.plataforma.persistencia.sqlite_colecciones import (
    BaseColeccionesSQLite,
    ListaSQLite,
    MapaSQLite,
)

from ..domain.modelos import Movimiento


class ActivosSQLite:
    def __init__(self, ruta: str | Path) -> None:
        base = BaseColeccionesSQLite(ruta)
        self.tipos = MapaSQLite(base, "activos.tipos")
        self.sectores = MapaSQLite(base, "activos.sectores")
        self.activos = MapaSQLite(base, "activos.activos")
        self.reparaciones = MapaSQLite(base, "activos.reparaciones")
        self.impresora = MapaSQLite(base, "activos.impresora")
        self._movimientos = ListaSQLite(base, "activos.movimientos")

    def registrar_movimiento(self, movimiento: Movimiento) -> None:
        self._movimientos.append(movimiento)

    def movimientos(self) -> list[Movimiento]:
        return list(self._movimientos)
