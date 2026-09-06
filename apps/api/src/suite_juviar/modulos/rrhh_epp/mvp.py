"""Armado de la aplicación: qué adaptador se enchufa a cada puerto.

Este es el único archivo que hay que tocar el día que aparezca la conexión a
Nexus. Se cambia la variable de entorno y listo:

    FUENTE_LEGAJOS=yaml    -> lee data/nexus_simulado.yaml   (hoy)
    FUENTE_LEGAJOS=nexus   -> lee la Vista dbo.vw_legajos_activos
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from suite_juviar.plataforma.parametria.domain.perfiles_acceso import MapaPerfilesAcceso
from suite_juviar.plataforma.parametria.infrastructure.perfiles_acceso_yaml import (
    PerfilesAccesoYAML,
)

from .application.servicios_mvp import ConsultarLegajo, RegistrarEntrega
from .infrastructure.catalogo_yaml import CatalogoYAML
from .infrastructure.firma_simulada import FirmaSimulada
from .infrastructure.legajos_nexus import LegajosNexusSQLServer
from .infrastructure.legajos_yaml import LegajosYAML
from .infrastructure.persistencia_mvp import BaseLocal, BitacoraSQLite, EntregasSQLite

RAIZ = Path(__file__).resolve().parent
RAIZ_SUITE = RAIZ.parents[1]


class ErrorDeConfiguracion(Exception):
    pass


@dataclass
class Contenedor:
    legajos: object
    perfiles_acceso: MapaPerfilesAcceso
    catalogo: CatalogoYAML
    entregas: EntregasSQLite
    firma: FirmaSimulada
    bitacora: BitacoraSQLite
    consultar_legajo: ConsultarLegajo
    registrar_entrega: RegistrarEntrega
    entorno: str
    modo_simulado: bool


def construir(
    entorno: str | None = None,
    fuente_legajos: str | None = None,
    ruta_base: str | None = None,
) -> Contenedor:
    entorno = (entorno or os.getenv("SJ_ENTORNO") or os.getenv("ENTORNO") or "desarrollo").lower()
    fuente_legajos = (
        fuente_legajos
        or os.getenv("SJ_FUENTE_LEGAJOS")
        or os.getenv("FUENTE_LEGAJOS")
        or "yaml"
    ).lower()

    # Guarda: la fuente simulada no puede llegar a producción por descuido.
    # Es la diferencia entre una constancia de prueba y una que alguien
    # presente en una inspección creyendo que vale.
    if entorno == "produccion":
        raise ErrorDeConfiguracion(
            "El MVP de RRHH/EPP no arranca en producción hasta reemplazar "
            "autenticación local, SQLite y firma simulada por los servicios de plataforma."
        )

    identidad_declarada_habilitada = (
        os.getenv("SJ_HABILITAR_IDENTIDAD_DECLARADA", "").strip().upper()
        in {"1", "SI", "SÍ", "TRUE"}
    )
    if entorno != "prueba" and not identidad_declarada_habilitada:
        raise ErrorDeConfiguracion(
            "No hay autenticación real. Para una prueba exclusivamente local declare "
            "SJ_HABILITAR_IDENTIDAD_DECLARADA=SI; nunca use esta opción en una red compartida."
        )

    if fuente_legajos == "yaml":
        legajos = LegajosYAML(RAIZ / "data" / "nexus_simulado.yaml")
    elif fuente_legajos == "nexus":
        cadena = os.getenv("SJ_NEXUS_DSN") or os.getenv("NEXUS_CONEXION")
        if not cadena:
            raise ErrorDeConfiguracion(
                "Falta NEXUS_CONEXION (cadena ODBC al servidor de Santa Fe)."
            )
        legajos = LegajosNexusSQLServer(cadena)
    else:
        raise ErrorDeConfiguracion(
            f"FUENTE_LEGAJOS='{fuente_legajos}' no es válido. Use 'yaml' o 'nexus'."
        )

    catalogo = CatalogoYAML(
        RAIZ / "data" / "catalogo_rd068.yaml",
        RAIZ / "data" / "matriz_sector_puesto_epp.yaml",
        RAIZ / "data" / "vida_util_referencial.yaml",
        RAIZ / "data" / "catalogo_items.yaml",
    )
    perfiles_acceso = PerfilesAccesoYAML(
        RAIZ_SUITE / "plataforma" / "parametria" / "data" / "perfiles_acceso.yaml"
    )
    ruta_sqlite = (
        ruta_base
        or os.getenv("SJ_RRHH_EPP_BASE_LOCAL")
        or Path.cwd() / "var" / "rrhh_epp" / "entregas_prueba.sqlite3"
    )
    base = BaseLocal(ruta_sqlite)
    entregas = EntregasSQLite(base)
    bitacora = BitacoraSQLite(base)
    firma = FirmaSimulada()

    return Contenedor(
        legajos=legajos,
        perfiles_acceso=perfiles_acceso,
        catalogo=catalogo,
        entregas=entregas,
        firma=firma,
        bitacora=bitacora,
        consultar_legajo=ConsultarLegajo(legajos, catalogo, entregas),
        registrar_entrega=RegistrarEntrega(legajos, catalogo, entregas, firma, bitacora),
        entorno=entorno,
        modo_simulado=(fuente_legajos != "nexus"),
    )
