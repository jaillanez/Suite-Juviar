from pathlib import Path

from fastapi.testclient import TestClient

from suite_juviar.modulos.capacitacion.api.app import crear_app
from suite_juviar.modulos.capacitacion.infrastructure.configuracion_yaml import (
    ConfiguracionCapacitacionYAML,
)


def cliente() -> TestClient:
    ruta = Path(__file__).parents[2] / "src/suite_juviar/modulos/capacitacion/data/configuracion.yaml"
    configuracion = ConfiguracionCapacitacionYAML(ruta)
    return TestClient(
        crear_app(configuracion), headers={"X-Perfil-Simulado": "RRHH"}
    )


def test_recorrido_tema_dictado_asistencia_y_planilla():
    c = cliente()
    tema = c.post("/temas", json={"nombre": "Uso de extintores", "horas": 2}).json()
    dictado = c.post("/dictados", json={"tema_id": tema["id"], "fecha": "2026-09-07", "instructor": "HyS"})
    assert dictado.status_code == 201
    identificador = dictado.json()["id"]
    asistencia = c.post(f"/dictados/{identificador}/asistencias", json={"legajo": "1042", "nombre_completo": "Persona prueba", "presente": True})
    assert asistencia.status_code == 201
    assert asistencia.json()["estado_firma"] == "PENDIENTE_FIRMA_PAPEL"
    planilla = c.get(f"/dictados/{identificador}/planilla")
    assert "SIN VALIDEZ LEGAL" in planilla.text


def test_url_de_dictado_inexistente_se_rechaza():
    respuesta = cliente().post("/dictados/no-existe/asistencias", json={"legajo": "1", "nombre_completo": "Prueba", "presente": False})
    assert respuesta.status_code == 404
