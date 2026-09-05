"""Adaptador provisorio del mapa puesto/sector → perfil."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class ErrorDeMapaPerfiles(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReglaPerfil:
    perfil: str
    puestos_codigo: frozenset[str]
    sectores_codigo: frozenset[str]


class PerfilesAccesoYAML:
    PERFILES_VALIDOS = frozenset({"campo", "deposito", "bascula"})

    def __init__(self, ruta: str | Path) -> None:
        self._ruta = Path(ruta)
        datos = yaml.safe_load(self._ruta.read_text(encoding="utf-8")) or {}
        self._dueno_dato = str(datos.get("dueno_dato") or "").strip()
        self._estado = str(datos.get("estado") or "").strip().upper()
        if not self._dueno_dato:
            raise ErrorDeMapaPerfiles("El mapa de perfiles debe declarar dueno_dato.")
        if not self._estado:
            raise ErrorDeMapaPerfiles("El mapa de perfiles debe declarar su estado.")

        reglas: list[ReglaPerfil] = []
        for fila in datos.get("reglas") or []:
            perfil = str(fila.get("perfil") or "").strip().lower()
            if perfil not in self.PERFILES_VALIDOS:
                raise ErrorDeMapaPerfiles(f"Perfil desconocido en {self._ruta.name}: {perfil!r}.")
            reglas.append(
                ReglaPerfil(
                    perfil=perfil,
                    puestos_codigo=frozenset(
                        str(valor).strip().upper()
                        for valor in fila.get("puestos_codigo") or []
                    ),
                    sectores_codigo=frozenset(
                        str(valor).strip().upper()
                        for valor in fila.get("sectores_codigo") or []
                    ),
                )
            )
        if not reglas:
            raise ErrorDeMapaPerfiles(f"{self._ruta.name} no contiene reglas de acceso.")
        self._reglas = tuple(reglas)

    @property
    def dueno_dato(self) -> str:
        return self._dueno_dato

    @property
    def estado(self) -> str:
        return self._estado

    def resolver(self, puesto_codigo: str, sector_codigo: str) -> str | None:
        puesto = puesto_codigo.strip().upper()
        sector = sector_codigo.strip().upper()
        coincidencias = {
            regla.perfil
            for regla in self._reglas
            if puesto in regla.puestos_codigo or sector in regla.sectores_codigo
        }
        if len(coincidencias) > 1:
            raise ErrorDeMapaPerfiles(
                f"Puesto {puesto!r} y sector {sector!r} asignan perfiles incompatibles: "
                f"{', '.join(sorted(coincidencias))}."
            )
        return next(iter(coincidencias), None)
