from __future__ import annotations

from pathlib import Path

from suite_juviar.plataforma.persistencia.sqlite_colecciones import (
    BaseColeccionesSQLite,
    MapaSQLite,
)

from .simulados import AdjuntosCifradosMemoria


class AdjuntosCifradosSQLite(AdjuntosCifradosMemoria):
    def __init__(self, clave: bytes, ruta: str | Path) -> None:
        super().__init__(clave)
        self._filas = MapaSQLite(BaseColeccionesSQLite(ruta), "legajo.adjuntos")
