"""Contrato puro del mapa de perfiles operativos."""

from __future__ import annotations

from typing import Protocol


class MapaPerfilesAcceso(Protocol):
    @property
    def dueno_dato(self) -> str: ...

    @property
    def estado(self) -> str: ...

    def resolver(self, puesto_codigo: str, sector_codigo: str) -> str | None: ...
