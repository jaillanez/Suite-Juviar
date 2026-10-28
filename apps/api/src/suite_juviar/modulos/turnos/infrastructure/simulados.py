from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from ..domain.entidades import Fichada, Imputacion


class FuenteFichadasSimulada:
    simulada = True

    def __init__(self, fichadas: list[Fichada]):
        self._fichadas = fichadas

    def listar(self, desde: date, hasta: date) -> list[Fichada]:
        return [f for f in self._fichadas if desde <= f.momento.date() <= hasta]


class ExportadorArchivoSimulado:
    simulada = True

    def __init__(self, directorio: Path):
        self._directorio = directorio

    def exportar(self, imputaciones: list[Imputacion]) -> str:
        self._directorio.mkdir(parents=True, exist_ok=True)
        ruta = self._directorio / "novedades_simuladas.json"
        contenido = {
            "marca": "DATOS SIMULADOS — SIN VALIDEZ",
            "destino": "BANDEJA_LOCAL; NO ESCRIBE EN TIME",
            "novedades": [asdict(i) for i in imputaciones],
        }
        ruta.write_text(json.dumps(contenido, default=str, ensure_ascii=False), encoding="utf-8")
        return str(ruta)
