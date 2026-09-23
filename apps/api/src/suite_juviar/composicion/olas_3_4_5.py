"""Único lugar que conecta los puertos de las olas nuevas con adaptadores."""

from __future__ import annotations

import os
from pathlib import Path

from suite_juviar.modulos.capacitacion.api.app import crear_router as crear_capacitacion
from suite_juviar.modulos.capacitacion.infrastructure.configuracion_yaml import (
    ConfiguracionCapacitacionYAML,
)
from suite_juviar.modulos.epp_analitica.api.app import crear_router as crear_analitica
from suite_juviar.modulos.epp_analitica.application.servicios import AnalizarEPP
from suite_juviar.modulos.epp_analitica.infrastructure.simulados import (
    FuenteEntregasDesdePuerto,
    PreciosSimulados,
)
from suite_juviar.modulos.legajo.api.app import crear_router as crear_legajo
from suite_juviar.modulos.legajo.application.servicios import GestionarLegajo
from suite_juviar.modulos.legajo.infrastructure.simulados import (
    FuenteLegajosDesdePuerto,
)
from suite_juviar.modulos.legajo.infrastructure.sqlite import AdjuntosCifradosSQLite
from suite_juviar.modulos.salud.api.app import crear_router as crear_salud
from suite_juviar.modulos.salud.application.servicios import GestionarSalud
from suite_juviar.modulos.salud.infrastructure.simulados import (
    CatalogoDiagnosticoSimulado,
    FuenteLaboralSimulada,
)
from suite_juviar.modulos.salud.infrastructure.sqlite import (
    AdjuntosSaludCifradosSQLite,
    SaludSQLite,
)
from suite_juviar.modulos.seleccion.api.app import crear_router as crear_seleccion
from suite_juviar.modulos.seleccion.infrastructure.perfiles_yaml import CriteriosPerfilYAML
from suite_juviar.modulos.turnos.api.app import crear_router as crear_turnos
from suite_juviar.modulos.turnos.application.servicios import ConciliarTurnos
from suite_juviar.modulos.turnos.infrastructure.sqlite import (
    EstadoTurnosSQLite,
    ExportadorArchivoLocal,
    FuenteFichadasSQLite,
)


def construir_routers(rrhh):
    entorno = (os.getenv("SJ_ENTORNO") or os.getenv("ENTORNO") or "desarrollo").lower()
    clave_adjuntos = os.getenv("SJ_LEGAJO_CLAVE_PRUEBA", "0" * 32).encode()
    ruta_modulos = os.getenv("SJ_MODULOS_SQLITE_PATH") or str(
        Path(__file__).parents[3] / "datos" / "modulos.sqlite3"
    )
    analitica = AnalizarEPP(
        FuenteEntregasDesdePuerto(rrhh.entregas),
        PreciosSimulados(),
        int(os.getenv("SJ_EPP_MUESTRA_MINIMA") or "5"),
    )
    legajo = GestionarLegajo(
        FuenteLegajosDesdePuerto(rrhh.legajos),
        AdjuntosCifradosSQLite(clave_adjuntos, ruta_modulos),
    )
    salud = GestionarSalud(
        CatalogoDiagnosticoSimulado(), SaludSQLite(ruta_modulos),
        AdjuntosSaludCifradosSQLite(clave_adjuntos, ruta_modulos), FuenteLaboralSimulada(),
    )
    turnos = ConciliarTurnos(
        FuenteFichadasSQLite(ruta_modulos),
        ExportadorArchivoLocal(Path("var/turnos/bandeja")),
        estado=EstadoTurnosSQLite(ruta_modulos),
    )
    raiz_modulos = Path(__file__).parents[1] / "modulos"
    perfiles_seleccion = CriteriosPerfilYAML(
        raiz_modulos / "seleccion" / "data" / "criterios_perfil.yaml"
    )
    configuracion_capacitacion = ConfiguracionCapacitacionYAML(
        raiz_modulos / "capacitacion" / "data" / "configuracion.yaml"
    )
    return {
        "epp-analitica": crear_analitica(analitica, entorno),
        "legajo": crear_legajo(legajo, entorno),
        "salud": crear_salud(salud, entorno),
        "turnos": crear_turnos(turnos, entorno),
        "seleccion": crear_seleccion(perfiles_seleccion, entorno, ruta_modulos),
        "capacitaciones": crear_capacitacion(configuracion_capacitacion, entorno, ruta_modulos),
    }
