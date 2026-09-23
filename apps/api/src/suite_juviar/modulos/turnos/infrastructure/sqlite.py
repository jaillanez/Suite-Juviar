from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from suite_juviar.plataforma.persistencia.sqlite_colecciones import (
    BaseColeccionesSQLite,
    ListaSQLite,
    MapaSQLite,
)

from ..domain.entidades import Fichada, Imputacion


class EstadoTurnosSQLite:
    def __init__(self, ruta: str | Path) -> None:
        base = BaseColeccionesSQLite(ruta)
        self.cronogramas = ListaSQLite(base, "turnos.cronogramas")
        self.cambios = ListaSQLite(base, "turnos.cambios")
        self.imputaciones = MapaSQLite(base, "turnos.imputaciones")
        self.bandeja = ListaSQLite(base, "turnos.bandeja")


class FuenteFichadasSQLite:
    simulada = False

    def __init__(self, ruta: str | Path) -> None:
        self._fichadas = ListaSQLite(
            BaseColeccionesSQLite(ruta), "turnos.fichadas_importadas"
        )

    def guardar(self, fichada: Fichada) -> None:
        self._fichadas.append(fichada)

    def listar(self, desde: date, hasta: date) -> list[Fichada]:
        return [f for f in self._fichadas if desde <= f.momento.date() <= hasta]


class ExportadorArchivoLocal:
    simulada = False

    def __init__(self, directorio: Path):
        self._directorio = directorio

    def exportar(self, imputaciones: list[Imputacion]) -> str:
        self._directorio.mkdir(parents=True, exist_ok=True)
        ruta = self._directorio / "novedades_turnos.json"
        ruta.write_text(
            json.dumps(
                {"novedades": [asdict(i) for i in imputaciones]},
                default=str,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return str(ruta)
