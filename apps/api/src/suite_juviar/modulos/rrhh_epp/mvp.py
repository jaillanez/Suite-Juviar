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

from .application.constancias import ObtenerConstanciaPDF
from .application.programadas import PlanificarEntregasProgramadas
from .application.servicios_mvp import ConsultarLegajo, RegistrarEntrega
from .domain.puertos_mvp import (
    Bitacora,
    MotorFirma,
    RepositorioConstancias,
    RepositorioEntregas,
    RepositorioStock,
)
from .infrastructure.catalogo_yaml import CatalogoYAML
from .infrastructure.constancia_pdf import GeneradorConstanciaPDFSimulada
from .infrastructure.firma_simulada import FirmaSimulada
from .infrastructure.legajos_nexus import LegajosNexusSQLServer
from .infrastructure.legajos_yaml import LegajosYAML
from .infrastructure.persistencia_mvp import (
    BaseLocal,
    BitacoraSQLite,
    ConfirmadorEntregaSQLite,
    ConstanciasSQLite,
    EntregasSQLite,
    StockSQLite,
)
from .infrastructure.persistencia_postgres import (
    BasePostgreSQL,
    BitacoraPostgreSQL,
    ConfirmadorEntregaPostgreSQL,
    ConstanciasPostgreSQL,
    EntregasPostgreSQL,
    EsquemaPostgreSQLFaltante,
    StockPostgreSQL,
)

RAIZ = Path(__file__).resolve().parent
RAIZ_SUITE = RAIZ.parents[1]


class ErrorDeConfiguracion(Exception):
    pass


@dataclass
class Contenedor:
    legajos: object
    perfiles_acceso: MapaPerfilesAcceso
    catalogo: CatalogoYAML
    entregas: RepositorioEntregas
    firma: MotorFirma
    bitacora: Bitacora
    consultar_legajo: ConsultarLegajo
    registrar_entrega: RegistrarEntrega
    obtener_constancia_pdf: ObtenerConstanciaPDF
    planificar_entregas: PlanificarEntregasProgramadas
    stock: RepositorioStock
    entorno: str
    modo_simulado: bool
    persistencia: str
    email_compras: str | None


def construir(
    entorno: str | None = None,
    fuente_legajos: str | None = None,
    ruta_base: str | None = None,
    persistencia: str | None = None,
    postgres_dsn: str | None = None,
    email_compras: str | None = None,
) -> Contenedor:
    entorno = (entorno or os.getenv("SJ_ENTORNO") or os.getenv("ENTORNO") or "desarrollo").lower()
    fuente_legajos = (
        fuente_legajos or os.getenv("SJ_FUENTE_LEGAJOS") or os.getenv("FUENTE_LEGAJOS") or "yaml"
    ).lower()
    email_compras = (email_compras or os.getenv("SJ_COMPRAS_EMAIL") or "").strip() or None
    if email_compras is not None and (
        "@" not in email_compras or email_compras.startswith("@") or email_compras.endswith("@")
    ):
        raise ErrorDeConfiguracion("SJ_COMPRAS_EMAIL no contiene una dirección válida.")

    catalogo = CatalogoYAML(
        RAIZ / "data" / "catalogo_rd068.yaml",
        RAIZ / "data" / "matriz_sector_puesto_epp.yaml",
        RAIZ / "data" / "vida_util_referencial.yaml",
        RAIZ / "data" / "catalogo_items.yaml",
    )

    # Guarda de arranque: enumera cada sustituto simulado que impide producción.
    if entorno == "produccion":
        bloqueos = [
            "autenticación real no integrada",
            "firma empresarial simulada",
        ]
        if fuente_legajos != "nexus":
            bloqueos.append("fuente de legajos distinta de Nexus")
        if catalogo.tiene_items_simulados:
            bloqueos.append("catálogo con ítems SIM-*")
        raise ErrorDeConfiguracion(
            "RRHH/EPP no arranca en producción: " + "; ".join(bloqueos) + "."
        )

    identidad_declarada_habilitada = os.getenv(
        "SJ_HABILITAR_IDENTIDAD_DECLARADA", ""
    ).strip().upper() in {"1", "SI", "SÍ", "TRUE"}
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

    perfiles_acceso = PerfilesAccesoYAML(
        RAIZ_SUITE / "plataforma" / "parametria" / "data" / "perfiles_acceso.yaml"
    )
    tipo_persistencia = (
        persistencia
        or os.getenv("SJ_RRHH_EPP_PERSISTENCIA")
        or ("sqlite" if entorno == "prueba" or ruta_base is not None else "postgresql")
    ).lower()
    constancias: RepositorioConstancias
    if tipo_persistencia == "sqlite":
        if entorno != "prueba" and ruta_base is None:
            raise ErrorDeConfiguracion(
                "SQLite quedó limitado a pruebas automatizadas. Use PostgreSQL en desarrollo local."
            )
        ruta_sqlite = ruta_base or ":memory:"
        base_sqlite = BaseLocal(ruta_sqlite)
        entregas = EntregasSQLite(base_sqlite)
        bitacora = BitacoraSQLite(base_sqlite)
        constancias = ConstanciasSQLite(base_sqlite)
        stock = StockSQLite(base_sqlite, RAIZ / "data" / "stock_inicial_simulado.yaml")
        confirmador = ConfirmadorEntregaSQLite(
            base_sqlite,
            entregas,
            stock,
            bitacora,
        )
    elif tipo_persistencia == "postgresql":
        dsn = (
            postgres_dsn
            or os.getenv("SJ_RRHH_EPP_DATABASE_URL")
            or "postgresql:///juviar_suite_local"
        )
        try:
            base_postgres = BasePostgreSQL(dsn)
        except EsquemaPostgreSQLFaltante as exc:
            raise ErrorDeConfiguracion(str(exc)) from exc
        entregas = EntregasPostgreSQL(base_postgres)
        bitacora = BitacoraPostgreSQL(base_postgres)
        constancias = ConstanciasPostgreSQL(base_postgres)
        stock = StockPostgreSQL(
            base_postgres,
            RAIZ / "data" / "stock_inicial_simulado.yaml",
        )
        confirmador = ConfirmadorEntregaPostgreSQL(base_postgres, stock)
    else:
        raise ErrorDeConfiguracion(
            f"SJ_RRHH_EPP_PERSISTENCIA='{tipo_persistencia}' no es válida. "
            "Use 'postgresql' o 'sqlite' sólo en pruebas."
        )
    firma = FirmaSimulada()
    generador_constancia = GeneradorConstanciaPDFSimulada()

    return Contenedor(
        legajos=legajos,
        perfiles_acceso=perfiles_acceso,
        catalogo=catalogo,
        entregas=entregas,
        firma=firma,
        bitacora=bitacora,
        consultar_legajo=ConsultarLegajo(legajos, catalogo, entregas),
        registrar_entrega=RegistrarEntrega(
            legajos,
            catalogo,
            entregas,
            firma,
            confirmador,
            permitir_items_simulados=entorno == "prueba",
        ),
        obtener_constancia_pdf=ObtenerConstanciaPDF(
            entregas,
            constancias,
            generador_constancia,
        ),
        planificar_entregas=PlanificarEntregasProgramadas(legajos, catalogo),
        stock=stock,
        entorno=entorno,
        modo_simulado=(
            fuente_legajos != "nexus"
            or catalogo.tiene_items_simulados
            or isinstance(firma, FirmaSimulada)
        ),
        persistencia=tipo_persistencia,
        email_compras=email_compras,
    )
