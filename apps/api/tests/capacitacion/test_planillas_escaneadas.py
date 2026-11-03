import base64
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from suite_juviar.modulos.capacitacion.api.app import crear_app
from suite_juviar.modulos.capacitacion.domain.modelos import FilaPlanilla
from suite_juviar.modulos.capacitacion.infrastructure.configuracion_yaml import (
    ConfiguracionCapacitacionYAML,
)
from suite_juviar.modulos.capacitacion.infrastructure.lector_planillas import LectorPlanillasIA

from .test_informe_anual import PADRON

FOTO = base64.b64encode(b"\x89PNG\r\n\x1a\nfoto de la planilla").decode()


class LectorFalso:
    """Simula una lectura con IA: 100 firmó, 200 no, y alguien se anotó a mano."""

    def __init__(self):
        self.esperados = None

    def leer(self, nombre, contenido, esperados):
        self.esperados = esperados
        return [FilaPlanilla("100", "Pérez Ana", True), FilaPlanilla("200", "Gómez Luis", False),
                FilaPlanilla("555", "Anotado A Mano", None)], "prueba", "Revisá"


def preparar(lector=None):
    ruta = Path(__file__).parents[2] / "src/suite_juviar/modulos/capacitacion/data/configuracion.yaml"
    base = str(Path(tempfile.mkdtemp()) / "modulos.sqlite3")
    app = crear_app(ConfiguracionCapacitacionYAML(ruta), ruta_base=base, padron=PADRON, lector=lector)
    c = TestClient(app, headers={"X-Perfil-Simulado": "RRHH", "X-Actor-Simulado": "rrhh.ana"})
    tema = c.post("/temas", json={"nombre": "Trabajo en altura", "horas": 2}).json()["id"]
    dictado = c.post("/dictados", json={"tema_id": tema, "fecha": "2026-06-01", "instructor": "HyS",
                                        "convocatoria_tipo": "LISTA", "convocados": ["100", "200"]}).json()["id"]
    return c, dictado


def _cargar(c, dictado, nombre="planilla.png"):
    return c.post(f"/dictados/{dictado}/planillas-escaneadas", json={"nombre": nombre, "contenido_base64": FOTO})


def test_planilla_impresa_trae_convocados_y_anotados():
    c, dictado = preparar()
    c.post(f"/dictados/{dictado}/asistencias", json={"legajo": "300", "nombre_completo": "Díaz Carla", "presente": True})
    texto = c.get(f"/dictados/{dictado}/planilla").text
    assert "100 | Pérez Ana" in texto and "200 | Gómez Luis" in texto and "300 | Díaz Carla" in texto


def test_planilla_queda_pendiente_y_al_aprobar_carga_presentes_y_ausentes():
    lector = LectorFalso()
    c, dictado = preparar(lector)
    # 100 ya estaba anotado esperando la firma en papel: la planilla la confirma.
    c.post(f"/dictados/{dictado}/asistencias", json={"legajo": "100", "nombre_completo": "Pérez Ana", "presente": True})

    cargada = _cargar(c, dictado)
    assert cargada.status_code == 201
    planilla = cargada.json()
    assert planilla["estado"] == "PENDIENTE" and planilla["cargada_por"] == "rrhh.ana"
    assert [f.legajo for f in lector.esperados] == ["100", "200"]
    assert [p["id"] for p in c.get("/planillas-escaneadas?estado=PENDIENTE").json()] == [planilla["id"]]
    assert c.get(f"/planillas-escaneadas/{planilla['id']}").json()["contenido_base64"] == FOTO
    # Hasta aprobar no se tocan las asistencias.
    assert len(c.get(f"/dictados/{dictado}/asistencias").json()) == 1

    sin_decidir = c.post(f"/planillas-escaneadas/{planilla['id']}/aprobar", json={"filas": planilla["filas"]})
    assert sin_decidir.status_code == 400

    filas = planilla["filas"]
    filas[2]["presente"] = True
    aprobada = c.post(f"/planillas-escaneadas/{planilla['id']}/aprobar", json={"filas": filas}).json()
    assert aprobada["estado"] == "APROBADA" and aprobada["revisada_por"] == "rrhh.ana"
    assert aprobada["resultado"] == {"presentes": 1, "ausentes": 1, "firmas_confirmadas": 1, "sin_cambios": []}
    estados = {a["participante"]["legajo"]: (a["presente"], a["estado_firma"])
               for a in c.get(f"/dictados/{dictado}/asistencias").json()}
    assert estados == {"100": (True, "FIRMADA_EN_PAPEL"), "200": (False, "AUSENTE"),
                       "555": (True, "FIRMADA_EN_PAPEL")}
    assert c.post(f"/planillas-escaneadas/{planilla['id']}/aprobar", json={"filas": filas}).status_code == 400


def test_no_pisa_lo_ya_registrado_ni_lo_anulado():
    c, dictado = preparar(LectorFalso())
    c.post(f"/dictados/{dictado}/asistencias", json={"legajo": "100", "nombre_completo": "Pérez Ana",
                                                     "presente": True, "metodo_firma": "TRAZO_TABLET",
                                                     "evidencia_firma": "trazo"})
    c.post(f"/dictados/{dictado}/asistencias", json={"legajo": "200", "nombre_completo": "Gómez Luis", "presente": True})
    c.post(f"/dictados/{dictado}/asistencias/200/anular", json={"motivo": "Error"})
    planilla = _cargar(c, dictado).json()
    filas = [{"legajo": "100", "nombre_completo": "Pérez Ana", "presente": True},
             {"legajo": "200", "nombre_completo": "Gómez Luis", "presente": True}]
    aprobada = c.post(f"/planillas-escaneadas/{planilla['id']}/aprobar", json={"filas": filas}).json()
    assert aprobada["resultado"]["sin_cambios"] == ["100", "200"]


def test_filas_invalidas_y_descarte():
    c, dictado = preparar(LectorFalso())
    planilla = _cargar(c, dictado).json()
    repetidas = [{"legajo": "100", "nombre_completo": "A", "presente": True}] * 2
    assert c.post(f"/planillas-escaneadas/{planilla['id']}/aprobar", json={"filas": repetidas}).status_code == 400
    assert c.post(f"/planillas-escaneadas/{planilla['id']}/descartar", json={"motivo": " "}).status_code == 400
    descartada = c.post(f"/planillas-escaneadas/{planilla['id']}/descartar", json={"motivo": "Foto borrosa"}).json()
    assert descartada["estado"] == "DESCARTADA" and descartada["motivo_descarte"] == "Foto borrosa"
    assert c.get("/planillas-escaneadas?estado=PENDIENTE").json() == []


@pytest.mark.parametrize("nombre,contenido,codigo", [
    ("planilla.docx", FOTO, 400),
    ("planilla.png", "no-es-base64!!", 400),
    ("planilla.png", base64.b64encode(b"x" * (10 * 1024 * 1024 + 1)).decode(), 400),
])
def test_rechaza_archivos_invalidos(nombre, contenido, codigo):
    c, dictado = preparar(LectorFalso())
    r = c.post(f"/dictados/{dictado}/planillas-escaneadas", json={"nombre": nombre, "contenido_base64": contenido})
    assert r.status_code == codigo
    assert c.post("/dictados/nada/planillas-escaneadas",
                  json={"nombre": "p.png", "contenido_base64": FOTO}).status_code == 404


def test_sin_ia_las_filas_salen_de_la_planilla_impresa(monkeypatch):
    monkeypatch.delenv("SJ_CAPACITACION_IA_API_KEY", raising=False)
    filas, motor, _ = LectorPlanillasIA().leer("p.png", b"x", [FilaPlanilla("100", "Pérez Ana", None)])
    assert motor == "manual" and filas == [FilaPlanilla("100", "Pérez Ana", None)]


def test_con_ia_completa_lo_que_no_devolvio_y_respeta_el_nombre_impreso(monkeypatch):
    import json

    from suite_juviar.modulos.capacitacion.infrastructure import lector_planillas

    monkeypatch.setenv("SJ_CAPACITACION_IA_API_KEY", "clave")
    respuesta = {"choices": [{"message": {"content": "```json\n" + json.dumps({"filas": [
        {"legajo": "100", "nombre_completo": "Peres Ana", "firmo": True},
        {"legajo": "777", "nombre_completo": "Nuevo", "firmo": "si"},
    ]}) + "\n```"}}]}

    class Respuesta:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(respuesta).encode()

    monkeypatch.setattr(lector_planillas.urllib.request, "urlopen", lambda *a, **k: Respuesta())
    filas, motor, _ = LectorPlanillasIA().leer(
        "p.jpg", b"x", [FilaPlanilla("100", "Pérez Ana", None), FilaPlanilla("200", "Gómez Luis", None)])
    assert motor == "deepseek"
    assert filas == [FilaPlanilla("100", "Pérez Ana", True), FilaPlanilla("777", "Nuevo", None),
                     FilaPlanilla("200", "Gómez Luis", None)]
