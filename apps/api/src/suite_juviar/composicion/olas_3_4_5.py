"""Único lugar que conecta los puertos de las olas nuevas con adaptadores."""

from __future__ import annotations

import os
from pathlib import Path

from suite_juviar.modulos.capacitacion.api.app import crear_app as crear_capacitacion
from suite_juviar.modulos.capacitacion.infrastructure.configuracion_yaml import (
    ConfiguracionCapacitacionYAML,
)
from suite_juviar.modulos.epp_analitica.api.app import crear_app as crear_analitica
from suite_juviar.modulos.epp_analitica.application.servicios import AnalizarEPP
from suite_juviar.modulos.epp_analitica.infrastructure.simulados import (
    FuenteEntregasDesdePuerto,
    PreciosSimulados,
)
from suite_juviar.modulos.legajo.api.app import crear_app as crear_legajo
from suite_juviar.modulos.legajo.application.servicios import GestionarLegajo
from suite_juviar.modulos.legajo.infrastructure.simulados import (
    AdjuntosCifradosMemoria,
    FuenteLegajosDesdePuerto,
)
from suite_juviar.modulos.salud.api.app import crear_app as crear_salud
from suite_juviar.modulos.salud.application.servicios import GestionarSalud
from suite_juviar.modulos.salud.infrastructure.simulados import (
    AdjuntosSaludCifradosMemoria,
    CatalogoDiagnosticoSimulado,
    FuenteLaboralSimulada,
    SaludMemoria,
)
from suite_juviar.modulos.seleccion.api.app import crear_app as crear_seleccion
from suite_juviar.modulos.seleccion.infrastructure.perfiles_yaml import CriteriosPerfilYAML
from suite_juviar.modulos.turnos.api.app import crear_app as crear_turnos
from suite_juviar.modulos.turnos.application.servicios import ConciliarTurnos
from suite_juviar.modulos.turnos.infrastructure.simulados import (
    ExportadorArchivoSimulado,
    FuenteFichadasSimulada,
)


def construir_subaplicaciones(rrhh):
    entorno = (os.getenv("SJ_ENTORNO") or os.getenv("ENTORNO") or "desarrollo").lower()
    clave_adjuntos = os.getenv("SJ_LEGAJO_CLAVE_PRUEBA", "0" * 32).encode()
    analitica = AnalizarEPP(
        FuenteEntregasDesdePuerto(rrhh.entregas),
        PreciosSimulados(),
        int(os.getenv("SJ_EPP_MUESTRA_MINIMA") or "5"),
    )
    legajo = GestionarLegajo(
        FuenteLegajosDesdePuerto(rrhh.legajos), AdjuntosCifradosMemoria(clave_adjuntos)
    )
    salud = GestionarSalud(
        CatalogoDiagnosticoSimulado(), SaludMemoria(),
        AdjuntosSaludCifradosMemoria(clave_adjuntos), FuenteLaboralSimulada(),
    )
    turnos = ConciliarTurnos(
        FuenteFichadasSimulada([]),
        ExportadorArchivoSimulado(Path("var/turnos/bandeja")),
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
        "seleccion": crear_seleccion(perfiles_seleccion, entorno),
        "capacitaciones": crear_capacitacion(configuracion_capacitacion, entorno),
    }
