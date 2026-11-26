"""Plantillas de Meta para los avisos que inicia la empresa (infra/043)."""

import json
import re

import httpx
import pytest
from consulta_publica.bot import registrar_plantillas
from consulta_publica.bot.meta_cloud import ClienteMeta, ConfigMeta, ErrorMeta, ErrorPlantilla
from consulta_publica.bot.plantillas import CATALOGO, armar
from consulta_publica.bot.worker import enviar_avisos, enviar_avisos_personal, texto_aviso_micro

TELEFONO = "5492640000000"


def cliente(manejador, cuenta="999"):
    http = httpx.Client(transport=httpx.MockTransport(manejador))
    return ClienteMeta(ConfigMeta("TOKEN", "123", cuenta_id=cuenta), http)


# --- Catálogo -----------------------------------------------------------------------------

@pytest.mark.parametrize("plantilla", list(CATALOGO.values()), ids=list(CATALOGO))
def test_cada_plantilla_cumple_las_reglas_de_meta(plantilla):
    assert re.fullmatch(r"[a-z0-9_]{1,60}", plantilla.nombre)
    assert plantilla.categoria == "UTILITY" and plantilla.idioma == "es_AR"
    numeros = [int(n) for n in re.findall(r"\{\{(\d+)\}\}", plantilla.cuerpo)]
    assert numeros == list(range(1, len(numeros) + 1))  # en orden y sin saltear
    assert len(plantilla.ejemplos) == plantilla.variables and all(plantilla.ejemplos)
    cuerpo = plantilla.cuerpo.strip()
    assert not cuerpo.startswith("{{") and not cuerpo.endswith("}}")
    assert "\n" not in cuerpo and len(cuerpo) <= 1024
    registro = plantilla.para_registrar()
    assert registro["components"][0]["example"]["body_text"] == [list(plantilla.ejemplos)]


def test_el_texto_del_micro_es_el_de_la_plantilla():
    assert texto_aviso_micro("Rawson") == "Llegó el micro de personal del recorrido «Rawson»."
    assert CATALOGO["llegada_micro"].texto(["Rawson"]) == texto_aviso_micro("Rawson")


def test_parametros_que_no_cierran_salen_como_texto():
    assert armar("turnos_asignados", ["uno"]) is None
    assert armar("no_existe", ["x"]) is None
    assert armar(None, None) is None
    assert armar("llegada_micro", [""]) is None
    _, valores = armar("llegada_micro", ["Ruta\n40   norte"])
    assert valores == ["Ruta 40 norte"]  # Meta no acepta saltos de línea ni espacios de más


# --- Envío por Cloud API ------------------------------------------------------------------

def test_cuerpo_de_la_plantilla_para_cloud_api():
    pedidos = []

    def manejar(pedido):
        pedidos.append(json.loads(pedido.content))
        assert str(pedido.url) == "https://graph.facebook.com/v23.0/123/messages"
        return httpx.Response(200, json={"messages": [{"id": "wamid.P"}]})

    assert cliente(manejar).enviar_plantilla(TELEFONO, "llegada_micro", "es_AR", ["Rawson"]) == "wamid.P"
    assert pedidos == [{
        "messaging_product": "whatsapp", "recipient_type": "individual", "to": TELEFONO, "type": "template",
        "template": {"name": "llegada_micro", "language": {"code": "es_AR"},
                     "components": [{"type": "body", "parameters": [{"type": "text", "text": "Rawson"}]}]},
    }]


def test_plantilla_no_aprobada_es_un_error_de_plantilla():
    def manejar(_):
        return httpx.Response(404, json={"error": {"code": 132001, "message": "Template name does not exist"}})

    with pytest.raises(ErrorPlantilla) as error:
        cliente(manejar).enviar_plantilla(TELEFONO, "x", "es_AR", ["a"])
    assert error.value.codigo == 132001
    with pytest.raises(ErrorMeta) as otro:
        cliente(lambda _: httpx.Response(500, json={"error": {"code": 131000}})).enviar_texto(TELEFONO, "a")
    assert not isinstance(otro.value, ErrorPlantilla)


# --- Worker -------------------------------------------------------------------------------

class SalidaTexto:
    """Simulador o Chattigo: no mandan plantillas."""

    def __init__(self):
        self.textos = []

    def enviar_texto(self, telefono, texto):
        self.textos.append(texto)
        return f"wamid.t{len(self.textos)}"


class SalidaMeta(SalidaTexto):
    def __init__(self, aprobadas=("turnos_asignados", "llegada_micro", "mosto_virgen_demorado")):
        super().__init__()
        self.aprobadas = aprobadas
        self.plantillas = []

    def enviar_plantilla(self, telefono, nombre, idioma, parametros):
        if nombre not in self.aprobadas:
            raise ErrorPlantilla("HTTP 404", 132001)
        self.plantillas.append((telefono, nombre, idioma, parametros))
        return f"wamid.p{len(self.plantillas)}"


class Bot:
    def __init__(self, avisos):
        self.avisos, self.marcas = avisos, []

    def tomar_avisos(self):
        return self.avisos

    def marcar_aviso(self, id_, wamid, error, nota=None):
        self.marcas.append((id_, wamid, error, nota))

    def tomar_avisos_personal(self):
        return self.avisos

    marcar_aviso_personal = marcar_aviso


ASIGNADO = {"id": 1, "telefono": TELEFONO, "texto": "Hola, Juan. Te asignamos los días…",
            "plantilla": "turnos_asignados",
            "parametros": ["Juan", "Chimbas", "Syrah", "lunes 02/03", "sábado 07/03", "12 camiones"]}


def test_por_meta_el_aviso_sale_con_su_plantilla():
    bot, salida = Bot([ASIGNADO]), SalidaMeta()
    assert enviar_avisos(bot, salida) == 1
    assert salida.plantillas == [(TELEFONO, "turnos_asignados", "es_AR", ASIGNADO["parametros"])]
    assert salida.textos == [] and bot.marcas == [(1, "wamid.p1", None, None)]


def test_si_meta_no_aprobo_la_plantilla_sale_el_texto_y_queda_anotado():
    bot, salida = Bot([ASIGNADO]), SalidaMeta(aprobadas=())
    assert enviar_avisos(bot, salida) == 1
    assert salida.textos == [ASIGNADO["texto"]]
    [(id_, wamid, error, nota)] = bot.marcas
    assert (id_, wamid, error) == (1, "wamid.t1", None)
    assert "turnos_asignados" in nota and "132001" in nota


def test_en_el_simulador_y_por_chattigo_sigue_saliendo_el_texto():
    bot, salida = Bot([ASIGNADO]), SalidaTexto()
    assert enviar_avisos(bot, salida) == 1
    assert salida.textos == [ASIGNADO["texto"]] and bot.marcas == [(1, "wamid.t1", None, None)]


def test_aviso_sin_plantilla_o_de_antes_de_043_sale_como_texto():
    viejo = {"id": 2, "telefono": TELEFONO, "texto": "Aviso de antes"}  # tomar_avisos sin las columnas nuevas
    bot, salida = Bot([viejo]), SalidaMeta()
    assert enviar_avisos(bot, salida) == 1
    assert salida.textos == ["Aviso de antes"] and salida.plantillas == []


def test_micro_por_plantilla_y_certificado_como_respuesta():
    avisos = [{"id": 1, "telefono": TELEFONO, "tipo": "micro", "recorrido": "Rawson", "texto": None},
              {"id": 2, "telefono": TELEFONO, "tipo": "certificado", "recorrido": None, "texto": "Leímos tu…"}]
    bot, salida = Bot(avisos), SalidaMeta()
    assert enviar_avisos_personal(bot, salida) == 2
    assert salida.plantillas == [(TELEFONO, "llegada_micro", "es_AR", ["Rawson"])]
    assert salida.textos == ["Leímos tu…"]


def test_con_el_cliente_de_meta_de_punta_a_punta():
    """Primero la plantilla (rechazada por no aprobada) y después el texto, contra Cloud API simulada."""
    tipos = []

    def manejar(pedido):
        cuerpo = json.loads(pedido.content)
        tipos.append(cuerpo["type"])
        if cuerpo["type"] == "template":
            return httpx.Response(400, json={"error": {"code": 132001, "message": "no existe"}})
        return httpx.Response(200, json={"messages": [{"id": "wamid.T"}]})

    bot = Bot([ASIGNADO])
    assert enviar_avisos(bot, cliente(manejar)) == 1
    assert tipos == ["template", "text"] and bot.marcas[0][1] == "wamid.T" and bot.marcas[0][3]


# --- Registro de las plantillas -----------------------------------------------------------

def graph_de_plantillas(existentes: dict[str, str]):
    creadas = []

    def manejar(pedido):
        assert pedido.url.path == "/v23.0/999/message_templates"
        if pedido.method == "GET":
            nombre = pedido.url.params.get("name")
            datos = [{"name": nombre, "language": "es_AR", "status": existentes[nombre]}] if nombre in existentes else []
            return httpx.Response(200, json={"data": datos})
        cuerpo = json.loads(pedido.content)
        creadas.append(cuerpo)
        return httpx.Response(200, json={"id": "1", "status": "PENDING", "category": cuerpo["category"]})

    return manejar, creadas


def test_registrar_crea_solo_las_que_faltan():
    manejar, creadas = graph_de_plantillas({"turnos_asignados": "APPROVED", "llegada_micro": "PENDING"})
    lineas = []
    assert registrar_plantillas.registrar(cliente(manejar), salida=lineas.append) == 0
    assert sorted(c["name"] for c in creadas) == ["mosto_virgen_demorado", "oferta_postergada"]
    assert all(c["language"] == "es_AR" and c["category"] == "UTILITY" for c in creadas)
    assert creadas[0]["components"][0]["example"]["body_text"]
    assert "turnos_asignados: APPROVED" in lineas and "llegada_micro: PENDING" in lineas


def test_listar_no_crea_nada():
    manejar, creadas = graph_de_plantillas({"turnos_asignados": "APPROVED"})
    lineas = []
    assert registrar_plantillas.registrar(cliente(manejar), listar=True, salida=lineas.append) == 0
    assert creadas == [] and "oferta_postergada: no está en la cuenta" in lineas


def test_si_meta_rechaza_una_sigue_con_las_demas():
    def manejar(pedido):
        if pedido.method == "GET":
            return httpx.Response(200, json={"data": []})
        if json.loads(pedido.content)["name"] == "turnos_asignados":
            return httpx.Response(400, json={"error": {"code": 100, "message": "Invalid parameter"}})
        return httpx.Response(200, json={"status": "PENDING"})

    lineas = []
    assert registrar_plantillas.registrar(cliente(manejar), salida=lineas.append) == 1
    assert sum("enviada a revisión" in linea for linea in lineas) == len(CATALOGO) - 1


def test_registrar_pide_token_y_cuenta(monkeypatch):
    monkeypatch.delenv("META_TOKEN", raising=False)
    monkeypatch.delenv("META_CUENTA_ID", raising=False)
    with pytest.raises(RuntimeError):
        registrar_plantillas.main(["x"])
    assert registrar_plantillas.main(["x", "--otra"]) == 2
