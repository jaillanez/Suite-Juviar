from datetime import date

import pytest
from fastapi.testclient import TestClient

from suite_juviar.modulos.salud.api.app import crear_app
from suite_juviar.modulos.salud.application.servicios import GestionarSalud
from suite_juviar.modulos.salud.domain.modelos import (
    AccesoSaludDenegado,
    FuenteSimuladaEnProduccion,
    ReporteNominadoProhibido,
)
from suite_juviar.modulos.salud.infrastructure.simulados import (
    CatalogoDiagnosticoSimulado,
    SaludMemoria,
)


def servicio():
    return GestionarSalud(CatalogoDiagnosticoSimulado(), SaludMemoria())


def test_rrhh_general_sin_rol_y_rol_nulo_no_ven_diagnostico():
    s = servicio()
    c = s.cargar("10", "MUESTRA-RESP", date(2026, 6, 1), date(2026, 6, 3))
    for rol in ("RRHH", "", None):
        with pytest.raises(AccesoSaludDenegado):
            s.consultar(c.id, "actor", rol)


def test_lectura_medica_deja_bitacora_y_control_negativo_del_guard(monkeypatch):
    s = servicio()
    c = s.cargar("10", "MUESTRA-RESP", date(2026, 6, 1), date(2026, 6, 3))
    s.consultar(c.id, "medico-1", "MEDICO")
    assert s.repositorio.consultas[0].actor == "medico-1"
    monkeypatch.setattr(s, "ROLES_LECTURA", frozenset({"MEDICO", "RRHH"}))
    assert s.consultar(c.id, "rrhh-1", "RRHH").id == c.id


def test_reporte_nominado_es_rechazado_y_art208_simulado_es_preliminar():
    s = servicio()
    with pytest.raises(ReporteNominadoProhibido):
        s.reporte_agregado(incluir_personas=True)
    assert s.aviso_articulo_208(500, 1, True) == {"aplica": True, "estado": "PRELIMINAR"}


def test_marca_visible_y_produccion_rechaza_catalogo_simulado():
    s = servicio()
    assert "DATOS SIMULADOS — SIN VALIDEZ" in TestClient(crear_app(s)).get("/").text
    with pytest.raises(FuenteSimuladaEnProduccion):
        crear_app(s, "produccion")


def test_api_rechaza_carga_y_consulta_sin_rol_medico():
    cliente = TestClient(crear_app(servicio()))
    cuerpo = {
        "legajo": "10",
        "diagnostico_codigo": "MUESTRA-RESP",
        "desde": "2026-06-01",
        "hasta": "2026-06-03",
    }
    assert cliente.post("/certificados", json=cuerpo).status_code == 403
    creado = cliente.post("/certificados", json=cuerpo, headers={"X-Rol": "MEDICO"})
    assert creado.status_code == 200
    identificador = creado.json()["id"]
    assert cliente.get(f"/certificados/{identificador}").status_code == 403
    assert cliente.get(
        f"/certificados/{identificador}", headers={"X-Rol": "RRHH", "X-Actor": "1"}
    ).status_code == 403
