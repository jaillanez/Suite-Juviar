from __future__ import annotations

from pathlib import Path

from suite_juviar.plataforma.persistencia.sqlite_colecciones import (
    BaseColeccionesSQLite,
    MapaSQLite,
)


class MostoSQLite:
    def __init__(self, ruta: str | Path) -> None:
        base = BaseColeccionesSQLite(ruta)
        self.compras = MapaSQLite(base, "mosto.compras")
        self.viajes = MapaSQLite(base, "mosto.viajes")
        self.avisos = MapaSQLite(base, "mosto.avisos")
        self.parametros = MapaSQLite(base, "mosto.parametros")
