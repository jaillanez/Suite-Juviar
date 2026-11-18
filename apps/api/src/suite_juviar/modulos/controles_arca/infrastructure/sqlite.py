from __future__ import annotations

from pathlib import Path

from suite_juviar.plataforma.persistencia.sqlite_colecciones import (
    BaseColeccionesSQLite,
    MapaSQLite,
)


class ControlesSQLite:
    def __init__(self, ruta: str | Path) -> None:
        base = BaseColeccionesSQLite(ruta)
        self.facturas = MapaSQLite(base, "controles_arca.facturas")
        self.parametros = MapaSQLite(base, "controles_arca.parametros")
        self.archivos = MapaSQLite(base, "controles_arca.archivos")
        self.padrones = MapaSQLite(base, "controles_arca.padrones")
        self.credenciales = MapaSQLite(base, "controles_arca.credenciales")
        # Permisos de acceso de WSAA (cifrados): ARCA no da otro mientras el anterior siga vigente.
        self.tickets = MapaSQLite(base, "controles_arca.tickets")
