from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from suite_juviar.modulos.epp_analitica.api.app import crear_app
from suite_juviar.modulos.epp_analitica.application.servicios import AnalizarEPP
from suite_juviar.modulos.epp_analitica.domain.modelos import (
    ExportacionNoPermitida,
    FuenteSimuladaEnProduccion,
    MovimientoEPP,
)
from suite_juviar.modulos.epp_analitica.infrastructure.simulados import (
    FuenteEntregasSimulada,
    PreciosSimulados,
)


def movimiento(n: int, reclamo=None):
    return MovimientoEPP(
        str(n), date(2026, 1, 1) + timedelta(days=n * 10), "10", "BOD", "OPE",
        "68", "SIM-68-01", 1, reclamo,
    )


def test_no_publica_promedio_con_muestra_insuficiente():
    servicio = AnalizarEPP(FuenteEntregasSimulada([movimiento(0)]), PreciosSimulados(), 2)
    metrica = servicio.metricas(date(2026, 1, 1), date(2026, 12, 31))[0]
    assert metrica.duracion_promedio_dias is None
    assert metrica.estado_duracion == "SIN_DATOS_SUFICIENTES"


def test_calcula_consumo_reclamos_y_duracion_suficiente():
    servicio = AnalizarEPP(
        FuenteEntregasSimulada([movimiento(0, "ROTURA"), movimiento(1), movimiento(2)]),
        PreciosSimulados(), 2,
    )
    metrica = servicio.metricas(date(2026, 1, 1), date(2026, 12, 31))[0]
    assert metrica.consumo == 3
    assert metrica.reclamos == {"ROTURA": 1}
    assert metrica.duracion_promedio_dias == 10


def test_precio_faltante_es_vacio_no_cero_y_exportacion_se_bloquea():
    servicio = AnalizarEPP(FuenteEntregasSimulada([movimiento(0)]), PreciosSimulados())
    costo = servicio.costos_por_persona(date(2026, 1, 1), date(2026, 12, 31))[0]
    assert costo.costo is None
    assert costo.faltante == "Falta precio real de Compras"
    with pytest.raises(ExportacionNoPermitida):
        servicio.exportar(date(2026, 1, 1), date(2026, 12, 31))


def test_pantalla_tiene_franja_visible_y_produccion_se_niega():
    servicio = AnalizarEPP(FuenteEntregasSimulada([movimiento(0)]), PreciosSimulados())
    html = TestClient(
        crear_app(servicio), headers={"X-Perfil-Simulado": "COMPRAS"}
    ).get("/", params={"desde": "2026-01-01", "hasta": "2026-12-31"}).text
    assert "DATOS SIMULADOS — SIN VALIDEZ" in html
    assert "@media print" in html
    with pytest.raises(FuenteSimuladaEnProduccion):
        crear_app(servicio, entorno="produccion")
