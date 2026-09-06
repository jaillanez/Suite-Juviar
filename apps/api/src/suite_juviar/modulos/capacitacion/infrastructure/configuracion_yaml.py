from __future__ import annotations

from pathlib import Path

import yaml


class ConfiguracionCapacitacionYAML:
    def __init__(self, ruta: str | Path) -> None:
        datos = yaml.safe_load(Path(ruta).read_text(encoding="utf-8")) or {}
        self._estado = str(datos.get("estado") or "DESCONOCIDO")
        self._dueno_dato = str(datos.get("dueno_dato") or "SIN_DEFINIR")
        self._umbral = float(datos["umbral_asistencia_supervisor"])

    @property
    def estado(self) -> str:
        return self._estado

    @property
    def dueno_dato(self) -> str:
        return self._dueno_dato

    @property
    def umbral_supervisor(self) -> float:
        return self._umbral

