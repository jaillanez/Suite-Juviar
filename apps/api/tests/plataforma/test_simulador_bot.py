from fastapi import FastAPI
from fastapi.testclient import TestClient

from suite_juviar.plataforma.terceros.api import simulador_bot

BODEGA = {"X-Perfil-Simulado": "BODEGA"}


def cliente():
    app = FastAPI()
    app.include_router(simulador_bot.router)
    return TestClient(app)


def test_sin_habilitar_no_manda_nada(monkeypatch):
    monkeypatch.delenv("SJ_SIMULADOR_BOT_HABILITADO", raising=False)
    monkeypatch.setenv("SJ_BOT_WEBHOOK_URL", "http://bot/webhook/secreto")
    enviados = []
    monkeypatch.setattr(simulador_bot.httpx, "post", lambda *a, **k: enviados.append(a))
    c = cliente()
    assert c.get("/simulador-bot/estado", headers=BODEGA).json() == {"habilitado": False}
    assert c.post("/simulador-bot/enviar", headers=BODEGA,
                  json={"telefono": "5492645551234", "texto": "hola"}).status_code == 503
    assert enviados == []
    assert c.get("/simulador-bot/estado", headers={"X-Perfil-Simulado": "MEDICO"}).status_code == 403


def test_manda_el_mensaje_como_whatsapp_y_lee_respuestas(monkeypatch):
    monkeypatch.setenv("SJ_SIMULADOR_BOT_HABILITADO", "si")
    monkeypatch.setenv("SJ_BOT_WEBHOOK_URL", "http://bot/webhook/secreto")
    monkeypatch.setenv("SJ_SIMULADOR_TELEFONOS", "5492645551234")
    enviados = []

    class Respuesta:
        status_code = 200

    def post(url, json, timeout):
        enviados.append((url, json))
        return Respuesta()

    monkeypatch.setattr(simulador_bot.httpx, "post", post)
    monkeypatch.setattr(simulador_bot, "_leer", lambda consulta, p: [{"id": 7, "texto": "Hola", "telefono": p.get("telefono")}])
    c = cliente()
    assert c.post("/simulador-bot/enviar", headers=BODEGA,
                  json={"telefono": "5492645551234", "texto": "Pedir turno"}).status_code == 200
    url, cuerpo = enviados[0]
    mensaje = cuerpo["entry"][0]["changes"][0]["value"]["messages"][0]
    assert url == "http://bot/webhook/secreto" and mensaje["text"]["body"] == "Pedir turno"
    assert mensaje["from"] == "5492645551234"
    r = c.get("/simulador-bot/respuestas", headers=BODEGA, params={"telefono": "5492645551234"}).json()
    assert r[0]["texto"] == "Hola"


def test_no_deja_hacerse_pasar_por_un_productor_real(monkeypatch):
    monkeypatch.setenv("SJ_SIMULADOR_BOT_HABILITADO", "si")
    monkeypatch.setenv("SJ_BOT_WEBHOOK_URL", "http://bot/webhook/secreto")
    monkeypatch.setenv("SJ_SIMULADOR_TELEFONOS", "5492645551234")
    monkeypatch.setattr(simulador_bot.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    c = cliente()
    assert c.post("/simulador-bot/enviar", headers=BODEGA,
                  json={"telefono": "5492640000000", "texto": "hola"}).status_code == 400
    assert c.get("/simulador-bot/respuestas", headers=BODEGA,
                 params={"telefono": "5492640000000"}).status_code == 400
    assert c.get("/simulador-bot/telefonos", headers=BODEGA).json() == [{"telefono": "5492645551234"}]
    monkeypatch.setenv("SJ_ENTORNO", "produccion")
    assert c.get("/simulador-bot/estado", headers=BODEGA).json() == {"habilitado": False}
