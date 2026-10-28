from datetime import date

import httpx
import pytest
from apps.simulador.main import crear_app, es_local, payload_meta
from consulta_publica.bot import configurar_webhook, transporte
from consulta_publica.bot.meta import extraer_mensajes
from fastapi.testclient import TestClient

LOCAL = ("127.0.0.1", 50000)


def app_simulada(manejador, monkeypatch):
    monkeypatch.setenv("SIM_WEBHOOK_URL", "http://172.18.0.1:8021/webhook/chattigo")
    monkeypatch.setenv("BOT_WEBHOOK_SECRETO", "s" * 48)
    return crear_app(httpx.Client(transport=httpx.MockTransport(manejador)))


@pytest.mark.parametrize("valor", ["", "whatsapp", "SIMULADO"])
def test_modo_invalido(monkeypatch, valor):
    monkeypatch.setenv("BOT_TRANSPORTE", valor)
    with pytest.raises(RuntimeError):
        transporte.modo()


def test_fecha_simulada_solo_en_simulador(monkeypatch):
    monkeypatch.setenv("BOT_TRANSPORTE", "simulado")
    monkeypatch.setenv("BOT_FECHA_SIMULADA", "2026-03-03")
    assert transporte.fecha_hoy() == date(2026, 3, 3)
    monkeypatch.setenv("BOT_TRANSPORTE", "chattigo")
    with pytest.raises(RuntimeError):
        transporte.desde_entorno()


def test_no_registra_webhook_real_en_simulado(monkeypatch, capsys):
    monkeypatch.setenv("BOT_TRANSPORTE", "simulado")
    assert configurar_webhook.main(["x", "https://ejemplo/webhook/chattigo"]) == 1
    assert "no es 'chattigo'" in capsys.readouterr().out


def test_payload_es_formato_meta():
    [mensaje] = extraer_mensajes(
        payload_meta("5490000000001", "hoy", "sim.in.x", 1760000000)
    )
    assert (mensaje.telefono, mensaje.texto, mensaje.wamid) == (
        "5490000000001", "hoy", "sim.in.x"
    )


def test_envia_al_webhook_real(monkeypatch):
    capturado = {}
    def manejar(pedido):
        capturado["url"] = str(pedido.url)
        return httpx.Response(200, json={"recibidos": 1, "nuevos": 1})
    cliente = TestClient(app_simulada(manejar, monkeypatch), client=LOCAL)
    respuesta = cliente.post(
        "/enviar", json={"telefono": "5490000000001", "texto": "2"}
    )
    assert respuesta.status_code == 200
    assert capturado["url"].endswith("/webhook/chattigo/" + "s" * 48)


def test_webhook_fallido_se_muestra(monkeypatch):
    cliente = TestClient(
        app_simulada(lambda _: httpx.Response(404), monkeypatch), client=LOCAL
    )
    assert cliente.post(
        "/enviar", json={"telefono": "5490000000001", "texto": "1"}
    ).status_code == 502


def test_rechaza_telefono_invalido(monkeypatch):
    cliente = TestClient(
        app_simulada(lambda _: httpx.Response(200), monkeypatch), client=LOCAL
    )
    assert cliente.post("/enviar", json={"telefono": "abc", "texto": "1"}).status_code == 422


def test_rechaza_origen_no_loopback(monkeypatch):
    cliente = TestClient(
        app_simulada(lambda _: httpx.Response(200), monkeypatch),
        client=("203.0.113.9", 1),
    )
    assert cliente.get("/").status_code == 403
    assert cliente.post(
        "/enviar", json={"telefono": "5490000000001", "texto": "1"}
    ).status_code == 403


@pytest.mark.parametrize(
    ("host", "esperado"),
    [("127.0.0.1", True), ("::1", True), ("10.0.0.5", False),
     ("173.212.195.122", False), ("testclient", False), (None, False)],
)
def test_es_local(host, esperado):
    assert es_local(host) is esperado
