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
    assert "DATOS SIMULADOS — SIN VALIDEZ" in TestClient(crear_app(s)).get("/1").text


def test_adjunto_conserva_original_y_no_persiste_en_claro():
    s = servicio()
    original = b"PDF original firmado e intacto"
    adjunto = s.adjuntar("1", "certificado.pdf", original)
    assert s.adjuntos.obtener(adjunto.id).contenido == original
    assert original not in s.adjuntos.bytes_persistidos(adjunto.id)


def test_produccion_rechaza_fuente_simulada():
    with pytest.raises(FuenteSimuladaEnProduccion):
        crear_app(servicio(), "produccion")
