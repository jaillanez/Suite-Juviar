from __future__ import annotations

from pathlib import Path

from suite_juviar.plataforma.persistencia.sqlite_colecciones import (
    BaseColeccionesSQLite,
    MapaSQLite,
)

from .memoria import CapacitacionEnMemoria


class CapacitacionSQLite(CapacitacionEnMemoria):
    """Mismo puerto del dominio, respaldado por SQLite en cada operación."""

    def __init__(self, ruta: str | Path) -> None:
        base = BaseColeccionesSQLite(ruta)
        self.temas = MapaSQLite(base, "capacitacion.temas")
        self.dictados = MapaSQLite(base, "capacitacion.dictados")
        self.asistencias = MapaSQLite(base, "capacitacion.asistencias")
        self.anulaciones = MapaSQLite(base, "capacitacion.anulaciones")
