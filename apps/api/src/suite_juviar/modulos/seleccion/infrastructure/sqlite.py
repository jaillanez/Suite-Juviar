from __future__ import annotations

from pathlib import Path

from suite_juviar.plataforma.persistencia.sqlite_colecciones import (
    BaseColeccionesSQLite,
    ListaSQLite,
    MapaSQLite,
)

from .extracciones_memoria import ExtraccionesEnMemoria
from .memoria import OriginalesEnMemoria


class OriginalesSQLite(OriginalesEnMemoria):
    def __init__(self, ruta: str | Path) -> None:
        base = BaseColeccionesSQLite(ruta)
        self._por_id = MapaSQLite(base, "seleccion.originales")
        self._por_referencia = MapaSQLite(base, "seleccion.referencias")


class ExtraccionesSQLite(ExtraccionesEnMemoria):
    def __init__(self, ruta: str | Path) -> None:
        base = BaseColeccionesSQLite(ruta)
        self._datos = MapaSQLite(base, "seleccion.extracciones")
        self._confirmaciones = MapaSQLite(base, "seleccion.confirmaciones")
        self._consultas = ListaSQLite(base, "seleccion.consultas")


def busquedas_sqlite(ruta: str | Path):
    return MapaSQLite(BaseColeccionesSQLite(ruta), "seleccion.busquedas")


def fichas_ia_sqlite(ruta: str | Path):
    return MapaSQLite(BaseColeccionesSQLite(ruta), "seleccion.fichas_ia")


def consultas_ia_sqlite(ruta: str | Path):
    return ListaSQLite(BaseColeccionesSQLite(ruta), "seleccion.consultas_ia")


def estados_cv_sqlite(ruta: str | Path):
    return MapaSQLite(BaseColeccionesSQLite(ruta), "seleccion.estados_cv")


def historial_estados_sqlite(ruta: str | Path):
    return ListaSQLite(BaseColeccionesSQLite(ruta), "seleccion.estados_historial")
