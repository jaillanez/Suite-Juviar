from __future__ import annotations

from pathlib import Path

from suite_juviar.plataforma.persistencia.sqlite_colecciones import (
    BaseColeccionesSQLite,
    ListaSQLite,
    MapaSQLite,
)

from .simulados import AdjuntosSaludCifradosMemoria, SaludMemoria


class SaludSQLite(SaludMemoria):
    def __init__(self, ruta: str | Path) -> None:
        base = BaseColeccionesSQLite(ruta)
        self.certificados = MapaSQLite(base, "salud.certificados")
        self.consultas = ListaSQLite(base, "salud.auditoria")


class AdjuntosSaludCifradosSQLite(AdjuntosSaludCifradosMemoria):
    def __init__(self, clave: bytes, ruta: str | Path) -> None:
        super().__init__(clave)
        self._filas = MapaSQLite(BaseColeccionesSQLite(ruta), "salud.adjuntos")
