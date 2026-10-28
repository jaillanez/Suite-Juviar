import base64
import json

import pytest
from fastapi.testclient import TestClient

from suite_juviar.modulos.legajo.api.app import crear_app
from suite_juviar.modulos.legajo.application.servicios import GestionarLegajo
from suite_juviar.modulos.legajo.domain.modelos import FuenteSimuladaEnProduccion, PersonaLegajo
from suite_juviar.modulos.legajo.infrastructure.simulados import (
    AdjuntosCifradosMemoria,
    FuenteLegajosSimulada,
)


def servicio():
    fuente = FuenteLegajosSimulada([
        PersonaLegajo("1", "Ana Pérez", "ENAV", "Bodega", "Operaria"),
        PersonaLegajo("2", "Juan Díaz", "Jubiar", "Finca", "Operario"),
    ])
    return GestionarLegajo(fuente, AdjuntosCifradosMemoria(b"0" * 32))


def test_formatos_por_empresa_y_marca_visible():
    s = servicio()
    assert s.ficha("1")["formato"] == "FICHA_ENAV"
    assert s.ficha("2")["formato"] == "FICHA_JUBIAR"
    cliente = TestClient(crear_app(s), headers={"X-Perfil-Simulado": "RRHH"})
    assert "DATOS SIMULADOS — SIN VALIDEZ" in cliente.get("/personas/1/formato").text
    assert "Ficha de personal Jubiar" in cliente.get("/personas/2/formato").text


def test_busqueda_por_todos_los_filtros_y_ficha_no_filtra_salud():
    cliente = TestClient(crear_app(servicio()), headers={"X-Perfil-Simulado": "RRHH"})
    assert [p["legajo"] for p in cliente.get("/personas", params={
        "apellido": "pérez", "legajo": "1", "sector": "bodega", "empresa": "enav",
    }).json()] == ["1"]
    respuesta = cliente.get("/personas/1")
    assert respuesta.status_code == 200
    serializado = json.dumps(respuesta.json()).casefold()
    for campo_medico in ("salud", "diagnostico", "enfermedad", "licencia"):
        assert campo_medico not in serializado
    assert respuesta.json()["origen"] == "Nexus"
    assert respuesta.json()["solo_lectura"] is True


def test_adjunto_conserva_original_y_no_persiste_en_claro():
    s = servicio()
    original = b"PDF original firmado e intacto"
    adjunto = s.adjuntar("1", "certificado.pdf", original)
    assert s.adjuntos.obtener(adjunto.id).contenido == original
    assert original not in s.adjuntos.bytes_persistidos(adjunto.id)


def test_adjunto_se_lista_se_recupera_y_su_baja_logica_conserva_el_original():
    s = servicio()
    cliente = TestClient(crear_app(s), headers={
        "X-Perfil-Simulado": "RRHH", "X-Actor-Simulado": "rrhh-1",
    })
    original = b"contenido firmado sin alteraciones"
    creado = cliente.post("/adjuntos", json={
        "legajo": "1", "nombre": "constancia.pdf",
        "contenido_base64": base64.b64encode(original).decode(),
    })
    assert creado.status_code == 200
    identificador = creado.json()["id"]
    assert cliente.get("/personas/1/adjuntos").json()[0]["activo"] is True
    assert base64.b64decode(cliente.get(f"/adjuntos/{identificador}").json()["contenido_base64"]) == original
    baja = cliente.post(f"/adjuntos/{identificador}/baja", json={"motivo": "Documento reemplazado"})
    assert baja.status_code == 200
    assert baja.json()["activo"] is False
    assert baja.json()["dado_baja_por"] == "rrhh-1"
    assert s.adjuntos.obtener(identificador).contenido == original


def test_permisos_de_legajo_se_aplican_en_la_api():
    cliente = TestClient(crear_app(servicio()))
    assert cliente.get("/personas").status_code == 401
    assert cliente.get("/personas", headers={"X-Perfil-Simulado": "MEDICO"}).status_code == 403
    assert cliente.get("/personas", headers={"X-Perfil-Simulado": "RRHH"}).status_code == 200


def test_produccion_rechaza_fuente_simulada():
    with pytest.raises(FuenteSimuladaEnProduccion):
        crear_app(servicio(), "produccion")
