import base64
import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from suite_juviar.modulos.capacitacion.api.app import crear_app
from suite_juviar.modulos.capacitacion.infrastructure.configuracion_yaml import (
    ConfiguracionCapacitacionYAML,
)


def cliente() -> TestClient:
    ruta = (
        Path(__file__).parents[2] / "src/suite_juviar/modulos/capacitacion/data/configuracion.yaml"
    )
    configuracion = ConfiguracionCapacitacionYAML(ruta)
    return TestClient(crear_app(configuracion), headers={"X-Perfil-Simulado": "RRHH"})


def test_recorrido_tema_dictado_asistencia_y_planilla():
    c = cliente()
    tema = c.post("/temas", json={"nombre": "Uso de extintores", "horas": 2}).json()
    dictado = c.post(
        "/dictados", json={"tema_id": tema["id"], "fecha": "2026-09-07", "instructor": "HyS"}
    )
    assert dictado.status_code == 201
    identificador = dictado.json()["id"]
    asistencia = c.post(
        f"/dictados/{identificador}/asistencias",
        json={"legajo": "1042", "nombre_completo": "Persona prueba", "presente": True},
    )
    assert asistencia.status_code == 201
    assert asistencia.json()["estado_firma"] == "PENDIENTE_FIRMA_PAPEL"
    planilla = c.get(f"/dictados/{identificador}/planilla")
    assert "SIN VALIDEZ LEGAL" in planilla.text


def test_url_de_dictado_inexistente_se_rechaza():
    respuesta = cliente().post(
        "/dictados/no-existe/asistencias",
        json={"legajo": "1", "nombre_completo": "Prueba", "presente": False},
    )
    assert respuesta.status_code == 404


def test_tandas_deduplican_persona_y_anulacion_permanece_auditada():
    c = cliente()
    tema = c.post("/temas", json={"nombre": "Bloqueo", "horas": 2}).json()
    ids = []
    for fecha in ("2026-09-07", "2026-09-08"):
        respuesta = c.post(
            "/dictados",
            json={
                "tema_id": tema["id"],
                "fecha": fecha,
                "instructor": "HyS",
                "duracion_horas": 2,
                "convocatoria_tipo": "LISTA",
                "convocatoria_detalle": "Personal expuesto",
                "convocados": ["1042", "1043"],
            },
        )
        assert respuesta.status_code == 201
        ids.append(respuesta.json()["id"])
    for dictado_id in ids:
        assert (
            c.post(
                f"/dictados/{dictado_id}/asistencias",
                json={
                    "legajo": "1042",
                    "nombre_completo": "Persona Uno",
                    "presente": True,
                },
            ).status_code
            == 201
        )
    c.post(
        f"/dictados/{ids[0]}/asistencias",
        json={
            "legajo": "1043",
            "nombre_completo": "Persona Dos",
            "presente": True,
        },
    )
    antes = c.get("/reportes", params={"tema_id": tema["id"]}).json()["tema"]
    assert antes["asistentes"] == 2
    assert antes["porcentaje"] == 100
    anulada = c.post(
        f"/dictados/{ids[0]}/asistencias/1043/anular",
        json={"motivo": "Carga duplicada"},
    )
    assert anulada.status_code == 200
    despues = c.get("/reportes", params={"tema_id": tema["id"]}).json()["tema"]
    assert despues["asistentes"] == 1
    assert despues["porcentaje"] == 50
    historial = c.get(f"/dictados/{ids[0]}/asistencias").json()
    registro = next(x for x in historial if x["participante"]["legajo"] == "1043")
    assert registro["anulada"] is True
    assert registro["anulacion"]["motivo"] == "Carga duplicada"


def test_api_rechaza_perfil_sin_permiso_y_sin_convocatoria_no_da_porcentaje():
    sin_permiso = TestClient(
        crear_app(
            ConfiguracionCapacitacionYAML(
                Path(__file__).parents[2]
                / "src/suite_juviar/modulos/capacitacion/data/configuracion.yaml"
            )
        ),
        headers={"X-Perfil-Simulado": "DEPOSITO"},
    )
    assert sin_permiso.get("/temas").status_code == 403
    c = cliente()
    tema = c.post("/temas", json={"nombre": "Sin denominador", "horas": 1}).json()
    d = c.post(
        "/dictados", json={"tema_id": tema["id"], "fecha": "2026-09-09", "instructor": "HyS"}
    ).json()
    c.post(
        f"/dictados/{d['id']}/asistencias",
        json={"legajo": "1", "nombre_completo": "Uno", "presente": True},
    )
    resumen = c.get("/reportes", params={"tema_id": tema["id"]}).json()["tema"]
    assert resumen["asistentes"] == 1
    assert resumen["porcentaje"] is None


def _xlsx_historico() -> bytes:
    filas = [
        [
            "tema",
            "horas",
            "fecha",
            "instructor",
            "duracion_horas",
            "convocatoria_tipo",
            "convocatoria_detalle",
            "convocados",
            "legajo",
            "nombre",
            "presente",
            "supervisor",
        ],
        [
            "Ergonomía",
            "1",
            "2026-04-01",
            "HyS",
            "1",
            "LISTA",
            "Administración",
            "3001",
            "3001",
            "Persona histórica",
            "si",
            "no",
        ],
    ]
    rows = "".join(
        "<row>" + "".join(f'<c t="inlineStr"><is><t>{v}</t></is></c>' for v in fila) + "</row>"
        for fila in filas
    )
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as z:
        z.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{rows}</sheetData></worksheet>',
        )
    return salida.getvalue()


def test_historico_se_previsualiza_y_aplica_sin_borrar_desapariciones():
    c = cliente()
    previa = c.post(
        "/historico/importaciones",
        json={"contenido_base64": base64.b64encode(_xlsx_historico()).decode()},
    )
    assert previa.status_code == 200
    assert previa.json()["total"] == 1
    assert previa.json()["agrega"] == ["Ergonomía|2026-04-01|3001"]
    aplicada = c.post(f"/historico/importaciones/{previa.json()['id']}/aplicar")
    assert aplicada.status_code == 200
    assert aplicada.json()["desapariciones_borradas"] == 0
    assert any(t["nombre"] == "Ergonomía" for t in c.get("/temas").json())


def test_historico_rechaza_archivo_invalido_y_perfil_sin_permiso():
    assert (
        cliente()
        .post(
            "/historico/importaciones",
            json={"contenido_base64": base64.b64encode(b"no es xlsx").decode()},
        )
        .status_code
        == 400
    )
    sin_permiso = TestClient(cliente().app, headers={"X-Perfil-Simulado": "DEPOSITO"})
    assert (
        sin_permiso.post(
            "/historico/importaciones",
            json={"contenido_base64": base64.b64encode(_xlsx_historico()).decode()},
        ).status_code
        == 403
    )
