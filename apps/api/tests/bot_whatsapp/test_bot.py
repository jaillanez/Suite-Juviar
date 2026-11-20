from datetime import UTC, date, datetime

import httpx
import pytest
from consulta_publica.api.descargas import Descarga
from consulta_publica.bot import webhook, worker
from consulta_publica.bot.chattigo import ClienteChattigo, ConfigChattigo, ErrorChattigo
from consulta_publica.bot.conversacion import MENU, NO_REGISTRADO, intencion, responder
from consulta_publica.bot.meta import MensajeEntrante, extraer_mensajes
from consulta_publica.bot.repositorio import Pendiente
from fastapi import FastAPI
from fastapi.testclient import TestClient

SECRETO = "s" * 48
HOY = date(2026, 3, 3)
TEXTO = {
    "from": "5492645123456",
    "id": "wamid.A",
    "timestamp": "1760000000",
    "type": "text",
    "text": {"body": "hoy"},
}


def payload(*mensajes, statuses=None):
    valor = {"messaging_product": "whatsapp", "messages": list(mensajes)}
    if statuses:
        valor["statuses"] = statuses
    return {"entry": [{"changes": [{"value": valor}]}]}


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [("1", "hoy"), ("descargas de hoy", "hoy"), ("ÚLTIMA", "ultima"),
     ("camión", "en_curso"), ("bascula", "en_curso"), ("hola", "menu"), (None, "menu")],
)
def test_intenciones(texto, esperada):
    assert intencion(texto) == esperada


def test_extrae_texto():
    [mensaje] = extraer_mensajes(payload(TEXTO))
    assert (mensaje.wamid, mensaje.telefono, mensaje.texto, mensaje.tipo) == (
        "wamid.A", "5492645123456", "hoy", "text"
    )
    assert mensaje.enviado_en is not None


def test_extrae_boton_interactivo():
    mensaje = {**TEXTO, "type": "interactive", "text": None,
               "interactive": {"button_reply": {"title": "Descargas de hoy"}}}
    assert extraer_mensajes(payload(mensaje))[0].texto == "Descargas de hoy"


def test_ignora_estados_imagen_y_telefono_invalido():
    solo_estado = payload(statuses=[{"id": "w", "status": "read"}])
    solo_estado["entry"][0]["changes"][0]["value"].pop("messages")
    assert extraer_mensajes(solo_estado) == []
    [imagen] = extraer_mensajes(payload({**TEXTO, "type": "image", "text": None}))
    assert imagen.texto is None
    assert extraer_mensajes(payload({**TEXTO, "from": "54 OR 1=1"})) == []


@pytest.mark.parametrize("basura", [None, [], "x", {"entry": None}, {"entry": [None]}])
def test_payload_malformado_no_rompe(basura):
    assert extraer_mensajes(basura) == []


class Consultas:
    def ultima(self, _):
        return Descarga("chimbas", "1", "9", datetime(2026, 3, 3, 12, 58, tzinfo=UTC), 11560,
                        "Cereza", 222.0, "descargado")

    def del_dia(self, _, __):
        return [
            Descarga("chimbas", "1", "1", None, 11560, "Cereza", None, "descargado"),
            Descarga("chimbas", "2", "2", None, 11740, "Cereza", None, "descargado"),
        ]

    def en_descarga(self, _):
        return [Descarga("chimbas", "3", "3", None, None, None, None, "en_descarga")]

    def datos_al(self):
        return {"chimbas": datetime(2026, 3, 3, 16, 0, tzinfo=UTC)}


def test_numero_no_registrado_no_recibe_datos():
    assert responder("1", [], Consultas(), HOY) == NO_REGISTRADO


def test_menu_y_respuestas_incluyen_sincronizacion():
    respuesta = responder("hola", ["J80"], Consultas(), HOY)
    assert MENU in respuesta and "03/03 13:00" in respuesta
    assert "2 descarga(s)" in responder("1", ["J80"], Consultas(), HOY)
    assert "23.300 kg" in responder("1", ["J80"], Consultas(), HOY)
    assert "11.560 kg" in responder("2", ["J80"], Consultas(), HOY)
    assert "1 camión(es)" in responder("3", ["J80"], Consultas(), HOY)


def test_dos_productores_no_exponen_cuit_ni_se_mezclan():
    respuesta = responder("3", ["J80", "J81"], Consultas(), HOY)
    assert "Productor 1" in respuesta and "Productor 2" in respuesta
    assert "J80" not in respuesta and "J81" not in respuesta


class Cola:
    def __init__(self):
        self.recibidos = []

    def encolar(self, mensaje):
        if mensaje.wamid in {m.wamid for m in self.recibidos}:
            return False
        self.recibidos.append(mensaje)
        return True


@pytest.fixture
def cliente_webhook(monkeypatch):
    monkeypatch.setenv("BOT_WEBHOOK_SECRETO", SECRETO)
    webhook._secreto.cache_clear()
    cola = Cola()
    app = FastAPI()
    app.include_router(webhook.router)
    app.dependency_overrides[webhook.obtener_cola] = lambda: cola
    cliente = TestClient(app)
    cliente.cola = cola
    yield cliente
    webhook._secreto.cache_clear()


def test_webhook_encola_y_deduplica(cliente_webhook):
    primera = cliente_webhook.post(f"/webhook/chattigo/{SECRETO}", json=payload(TEXTO))
    segunda = cliente_webhook.post(f"/webhook/chattigo/{SECRETO}", json=payload(TEXTO))
    assert primera.json() == {"recibidos": 1, "nuevos": 1}
    assert segunda.json() == {"recibidos": 1, "nuevos": 0}


@pytest.mark.parametrize("ruta", ["/webhook/chattigo", "/webhook/chattigo/", "/webhook/chattigo/x"])
def test_webhook_rechaza_secreto_ausente_o_incorrecto(cliente_webhook, ruta):
    assert cliente_webhook.post(ruta, json=payload(TEXTO)).status_code in (404, 405)
    assert cliente_webhook.cola.recibidos == []


def test_webhook_rechaza_json_y_cuerpo_enorme(cliente_webhook):
    ruta = f"/webhook/chattigo/{SECRETO}"
    assert cliente_webhook.post(ruta, content=b"{mal").status_code == 400
    assert cliente_webhook.post(ruta, content=b"x" * (webhook.TAMANO_MAXIMO + 1)).status_code == 413


@pytest.mark.parametrize("valor", [None, "", "corto", "x" * 47])
def test_configuracion_exige_secreto_de_48(monkeypatch, valor):
    if valor is None:
        monkeypatch.delenv("BOT_WEBHOOK_SECRETO", raising=False)
    else:
        monkeypatch.setenv("BOT_WEBHOOK_SECRETO", valor)
    with pytest.raises(RuntimeError):
        webhook.cargar_secreto()


CFG = ConfigChattigo("https://api.test", "u", "p", "did")


def cliente_chattigo(manejador, config=CFG):
    http = httpx.Client(transport=httpx.MockTransport(manejador))
    return ClienteChattigo(config, http)


def test_chattigo_reusa_token_y_payload_meta():
    logins = []
    def manejar(pedido):
        if pedido.url.path == "/login":
            logins.append(1)
            return httpx.Response(200, json={"access_token": "T"})
        assert pedido.headers["Authorization"] == "T"
        assert pedido.url.path == "/v15.0/did/messages"
        return httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})
    cliente = cliente_chattigo(manejar)
    assert cliente.enviar_texto("549", "a") == "wamid.X"
    cliente.enviar_texto("549", "b")
    assert len(logins) == 1


def test_chattigo_renueva_una_vez_ante_401():
    tokens = iter(["viejo", "nuevo"])
    def manejar(pedido):
        if pedido.url.path == "/login":
            return httpx.Response(200, json={"access_token": next(tokens)})
        if pedido.headers["Authorization"] == "viejo":
            return httpx.Response(401)
        return httpx.Response(200, json={"messages": [{"id": "ok"}]})
    assert cliente_chattigo(manejar).enviar_texto("549", "a") == "ok"


def test_chattigo_errores_y_webhook_https():
    with pytest.raises(ErrorChattigo):
        cliente_chattigo(lambda _: httpx.Response(400)).enviar_texto("549", "a")
    with pytest.raises(ValueError):
        cliente_chattigo(lambda _: httpx.Response(200)).configurar_webhook("http://inseguro")


class Bot:
    def __init__(self, pendientes, inscriptos=("J80",), respondidas=0):
        self.pendientes = pendientes
        self.inscriptos_valor = inscriptos
        self.respondidas = respondidas
        self.cerrados, self.reintentos, self.bitacora = [], [], []

    def tomar(self):
        salida, self.pendientes = self.pendientes, []
        return salida
    def productores(self, _): return list(self.inscriptos_valor)
    def respuestas_ultima_hora(self, _): return self.respondidas
    def cerrar(self, *args, **kwargs): self.cerrados.append((args, kwargs))
    def reintentar(self, *args): self.reintentos.append(args)
    def registrar_consulta(self, *args): self.bitacora.append(args)


class Chattigo:
    def __init__(self, falla=False): self.falla, self.enviados = falla, []
    def enviar_texto(self, telefono, texto):
        if self.falla:
            raise ErrorChattigo("HTTP 503")
        self.enviados.append((telefono, texto))
        return "wamid.salida"


PENDIENTE = Pendiente(1, "5492645123456", "2", 0)


def test_worker_responde_registra_y_reintenta():
    bot, chattigo = Bot([PENDIENTE]), Chattigo()
    assert worker.procesar_una_vez(bot, Consultas(), chattigo) == 1
    assert bot.cerrados[0][0][1] == "respondido"
    assert bot.bitacora == [("J80", "whatsapp:ultima", 0)]
    fallido = Bot([PENDIENTE])
    worker.procesar_una_vez(fallido, Consultas(), Chattigo(falla=True))
    assert fallido.reintentos and not fallido.cerrados


def test_worker_numero_desconocido_y_tope():
    desconocido, salida = Bot([PENDIENTE], inscriptos=()), Chattigo()
    worker.procesar_una_vez(desconocido, Consultas(), salida)
    assert salida.enviados[0][1] == NO_REGISTRADO and desconocido.bitacora == []
    limitado, salida = Bot([PENDIENTE], respondidas=20), Chattigo()
    worker.procesar_una_vez(limitado, Consultas(), salida, 20)
    assert not salida.enviados and limitado.cerrados[0][0][1] == "ignorado"


def test_mensaje_entrante_es_inmutable():
    mensaje = MensajeEntrante("w", "5492645123456", "text", "1", None)
    with pytest.raises(AttributeError):
        mensaje.texto = "2"


# --- Meta directo -------------------------------------------------------------
import hashlib
import hmac
import json

from consulta_publica.bot.meta_cloud import ClienteMeta, ConfigMeta, ErrorMeta

CLAVE_APP = "c" * 32
VERIFICACION = "v" * 32


@pytest.fixture
def cliente_meta(monkeypatch, cliente_webhook):
    monkeypatch.setenv("META_CLAVE_APP", CLAVE_APP)
    monkeypatch.setenv("META_TOKEN_VERIFICACION", VERIFICACION)
    return cliente_webhook


def firmado(cuerpo: bytes, clave: str = CLAVE_APP) -> dict[str, str]:
    firma = hmac.new(clave.encode(), cuerpo, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={firma}", "Content-Type": "application/json"}


def test_meta_verifica_la_direccion(cliente_meta):
    params = {"hub.mode": "subscribe", "hub.verify_token": VERIFICACION, "hub.challenge": "12345"}
    respuesta = cliente_meta.get("/webhook/meta", params=params)
    assert respuesta.status_code == 200 and respuesta.text == "12345"
    malo = {**params, "hub.verify_token": "otro"}
    assert cliente_meta.get("/webhook/meta", params=malo).status_code == 403


def test_meta_encola_solo_con_firma_valida(cliente_meta):
    cuerpo = json.dumps(payload(TEXTO)).encode()
    assert cliente_meta.post("/webhook/meta", content=cuerpo).status_code == 403
    assert cliente_meta.post("/webhook/meta", content=cuerpo,
                             headers=firmado(cuerpo, "x" * 32)).status_code == 403
    assert cliente_meta.cola.recibidos == []
    ok = cliente_meta.post("/webhook/meta", content=cuerpo, headers=firmado(cuerpo))
    assert ok.json() == {"recibidos": 1, "nuevos": 1}


def test_meta_sin_configurar_no_existe(cliente_webhook, monkeypatch):
    monkeypatch.delenv("META_CLAVE_APP", raising=False)
    monkeypatch.delenv("META_TOKEN_VERIFICACION", raising=False)
    assert cliente_webhook.post("/webhook/meta", json=payload(TEXTO)).status_code == 404
    assert cliente_webhook.get("/webhook/meta").status_code == 404


def cliente_graph(manejador):
    http = httpx.Client(transport=httpx.MockTransport(manejador))
    return ClienteMeta(ConfigMeta("TOKEN", "123", cuenta_id="999"), http)


def test_meta_envia_con_token_al_numero():
    def manejar(pedido):
        assert pedido.headers["Authorization"] == "Bearer TOKEN"
        assert str(pedido.url) == "https://graph.facebook.com/v23.0/123/messages"
        assert json.loads(pedido.content)["text"]["body"] == "hola"
        return httpx.Response(200, json={"messages": [{"id": "wamid.M"}]})
    assert cliente_graph(manejar).enviar_texto("549", "hola") == "wamid.M"


def test_meta_errores_se_reintentan_como_chattigo():
    with pytest.raises(ErrorChattigo):
        cliente_graph(lambda _: httpx.Response(400, text="x")).enviar_texto("549", "a")


def test_meta_baja_foto_solo_de_whatsapp():
    def manejar(pedido):
        if pedido.url.path == "/v23.0/MEDIA":
            return httpx.Response(200, json={"url": "https://lookaside.fbsbx.com/f", "mime_type": "image/jpeg"})
        assert pedido.url.host == "lookaside.fbsbx.com"
        return httpx.Response(200, content=b"x" * 2000)
    contenido, tipo = cliente_graph(manejar).descargar_media("MEDIA")
    assert len(contenido) == 2000 and tipo == "image/jpeg"
    with pytest.raises(ErrorMeta):
        cliente_graph(lambda _: httpx.Response(200, json={"url": "https://malo.com/f"})).descargar_media("M")


def test_meta_suscribe_la_cuenta():
    def manejar(pedido):
        assert pedido.method == "POST" and pedido.url.path == "/v23.0/999/subscribed_apps"
        return httpx.Response(200, json={"success": True})
    assert cliente_graph(manejar).suscribir_cuenta() == {"success": True}
