from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from suite_juviar.main import app
from suite_juviar.plataforma.terceros.api.conversaciones_bot import armar_chat

T0 = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def _fila(id_, texto, respuesta, estado="respondido", minutos=0, tipo="text"):
    return {"id": id_, "tipo": tipo, "texto": texto, "recibido_en": T0 + timedelta(minutes=minutos),
            "estado": estado, "respuesta": respuesta, "procesado_en": T0 + timedelta(minutes=minutos, seconds=2)}


def test_ordena_mensajes_y_respuestas_por_llegada():
    chat = armar_chat([_fila(2, "1", "Elegí el día", minutos=1), _fila(1, "Hola", "Menú")])
    assert [(m["de"], m["texto"]) for m in chat] == [
        ("persona", "Hola"), ("bot", "Menú"), ("persona", "1"), ("bot", "Elegí el día")]


def test_muestra_aviso_si_el_bot_no_respondio_y_tipo_si_no_hay_texto():
    chat = armar_chat([_fila(1, None, None, estado="ignorado", tipo="image")])
    assert chat[0]["texto"] == "[image]"
    assert chat[1]["de"] == "aviso"


def test_pendiente_sin_respuesta_no_agrega_burbuja_del_bot():
    assert len(armar_chat([_fila(1, "Hola", None, estado="pendiente")])) == 1


def test_sin_permiso_no_puede_leer_conversaciones():
    cliente = TestClient(app)
    respuesta = cliente.get("/api/v1/conversaciones-bot", headers={"X-Perfil-Simulado": "RRHH"})
    assert respuesta.status_code == 403
