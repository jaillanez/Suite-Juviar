from __future__ import annotations

from pathlib import Path

import yaml

from ..domain.modelos import PerfilBusqueda


class CriteriosPerfilYAML:
    def __init__(self, ruta: str | Path) -> None:
        datos = yaml.safe_load(Path(ruta).read_text(encoding="utf-8")) or {}
        self._estado = str(datos.get("estado") or "DESCONOCIDO")
        self._dueno_dato = str(datos.get("dueno_dato") or "SIN_DEFINIR")
        self._perfiles = datos.get("perfiles") or {}

    @property
    def estado(self) -> str:
        return self._estado

    @property
    def dueno_dato(self) -> str:
        return self._dueno_dato

    def palabras_clave(self, perfil: PerfilBusqueda) -> tuple[str, ...]:
        valores = self._perfiles.get(perfil.value) or []
        return tuple(str(valor) for valor in valores)

