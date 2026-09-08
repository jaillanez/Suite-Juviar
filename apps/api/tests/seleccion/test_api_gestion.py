from pathlib import Path

from fastapi.testclient import TestClient

from suite_juviar.modulos.seleccion.api.app import crear_app
from suite_juviar.modulos.seleccion.infrastructure.perfiles_yaml import CriteriosPerfilYAML


def cliente() -> TestClient:
    ruta = Path(__file__).parents[2] / "src/suite_juviar/modulos/seleccion/data/criterios_perfil.yaml"
    return TestClient(crear_app(CriteriosPerfilYAML(ruta)))


def test_busqueda_conserva_autor_y_criterio():
    respuesta = cliente().post("/busquedas", json={
        "nombre": "Temporada", "perfil": "BODEGA", "definido_por": "rrhh-1",
        "edad_minima": 18, "secundaria_completa": True,
    })
    assert respuesta.status_code == 201
    assert respuesta.json()["definido_por"] == "rrhh-1"
    assert respuesta.json()["definido_en"]


def test_lote_invalido_no_se_descarta_en_silencio():
    respuesta = cliente().post("/cvs/lote", json={"archivos": [{"nombre": "cv.pdf", "contenido_base64": "?"}]})
    assert respuesta.status_code == 400
    assert "base64" in respuesta.json()["detail"]
