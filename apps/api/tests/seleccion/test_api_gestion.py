import base64
import io
from pathlib import Path

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from suite_juviar.modulos.seleccion.api.app import crear_app
from suite_juviar.modulos.seleccion.infrastructure.perfiles_yaml import CriteriosPerfilYAML


def cliente() -> TestClient:
    ruta = Path(__file__).parents[2] / "src/suite_juviar/modulos/seleccion/data/criterios_perfil.yaml"
    return TestClient(
        crear_app(CriteriosPerfilYAML(ruta)),
        headers={"X-Perfil-Simulado": "RRHH"},
    )


def test_busqueda_conserva_autor_y_criterio():
    respuesta = cliente().post("/busquedas", json={
        "nombre": "Temporada", "perfil": "BODEGA", "definido_por": "rrhh-1",
        "edad_minima": 18, "secundaria_completa": True,
    })
    assert respuesta.status_code == 201
    assert respuesta.json()["definido_por"] == "rrhh-prueba"
    assert respuesta.json()["definido_en"]


def test_lote_invalido_no_se_descarta_en_silencio():
    respuesta = cliente().post("/cvs/lote", json={"archivos": [{"nombre": "cv.pdf", "contenido_base64": "?"}]})
    assert respuesta.status_code == 400
    assert "base64" in respuesta.json()["detail"]


def pdf(texto: str) -> bytes:
    salida = io.BytesIO()
    documento = canvas.Canvas(salida)
    documento.drawString(40, 800, texto)
    documento.save()
    return salida.getvalue()


def test_ilegible_va_a_revision_y_original_queda_auditado():
    c = cliente()
    carga = c.post("/cvs/lote", json={"archivos": [{
        "nombre": "ilegible.pdf",
        "contenido_base64": base64.b64encode(pdf("sin campos reconocibles")).decode(),
    }]})
    identificador = carga.json()["incorporados"][0]
    revision = c.get("/revision").json()
    assert [fila["id"] for fila in revision] == [identificador]
    assert c.get(f"/cvs/{identificador}/original").status_code == 200
    auditoria = c.get(f"/cvs/{identificador}/auditoria").json()
    assert auditoria[0]["actor"] == "rrhh-prueba"


def test_campo_requiere_confirmacion_explicita_con_autor():
    c = cliente()
    carga = c.post("/cvs/lote", json={"archivos": [{
        "nombre": "legible.pdf",
        "contenido_base64": base64.b64encode(pdf("Oficio: bodeguero")).decode(),
    }]})
    identificador = carga.json()["incorporados"][0]
    assert c.get(f"/cvs/{identificador}").json()["confirmaciones"] == []
    confirmado = c.put(
        f"/cvs/{identificador}/campos/oficio/confirmacion", json={"valor": "bodeguero"}
    )
    assert confirmado.status_code == 200
    assert confirmado.json()["confirmado_por"] == "rrhh-prueba"


def test_perfil_sin_permiso_recibe_403():
    c = TestClient(crear_app(CriteriosPerfilYAML(
        Path(__file__).parents[2] / "src/suite_juviar/modulos/seleccion/data/criterios_perfil.yaml"
    )))
    assert c.get("/busquedas", headers={"X-Perfil-Simulado": "HYS"}).status_code == 403
