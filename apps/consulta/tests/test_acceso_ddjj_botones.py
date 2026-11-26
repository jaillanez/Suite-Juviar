"""Recuperado del bot anterior: acceso por cuenta, CUIT o patente, comprobante DDJJ y botones."""

import json
from datetime import date, datetime

import httpx
from consulta_publica.bot.botones import cuerpo_opciones
from consulta_publica.bot.dialogo import (
    COMPROBANTE,
    DEMASIADOS_INTENTOS,
    DESVINCULADA,
    DESVINCULAR,
    ELEGIR_VINCULO,
    IDENTIFICAR,
    MENU,
    NO_REGISTRADO,
    PEDIR_DATO,
    VINCULAR,
    Cuenta,
    Estado,
    IdentificacionBloqueada,
    responder,
)
from consulta_publica.bot.meta import extraer_mensajes
from consulta_publica.bot.meta_cloud import ClienteMeta, ConfigMeta
from consulta_publica.bot.reporte_pdf import (
    Comprobante,
    generar_comprobante,
    nombre_comprobante,
)
from consulta_publica.bot.repositorio import Pendiente
from consulta_publica.bot.worker import procesar_una_vez

HOY = date(2026, 3, 17)
TELEFONO = "5492645550000"
ENAV = Cuenta("30500010912", "G03436", "ENAV S.A.")
PEREZ = Cuenta("20227149583", "J80158", "PEREZ JUAN.")
TODO = frozenset({"ver_informes", "pedir_turnos", "administrar_contactos"})


class Identificador:
    def __init__(self, resultado=(), bloqueado=False):
        self.resultado, self.bloqueado, self.pedidos = list(resultado), bloqueado, []

    def buscar(self, por, dato):
        self.pedidos.append((por, dato))
        if self.bloqueado:
            raise IdentificacionBloqueada()
        return self.resultado


def sin_alta(texto, estado=None, identificar=None, candidatas=None):
    return responder(texto, [], estado or Estado(), HOY, identificar=identificar or Identificador(),
                     candidatas=candidatas)


def abierta(texto, estado=None, **kw):
    return responder(texto, [PEREZ], estado or Estado(MENU, PEREZ.clientecuit), HOY,
                     sesion_abierta=True, **kw)


# --- Identificación ----------------------------------------------------------------------


def test_sin_identificador_sigue_el_aviso_de_no_registrado():
    assert responder("hola", [], Estado(), HOY).texto == NO_REGISTRADO


def test_numero_sin_alta_pide_cuenta_cuit_o_patente():
    respuesta = sin_alta("hola")
    assert respuesta.texto == PEDIR_DATO and respuesta.estado.paso == IDENTIFICAR
    assert "CV" in respuesta.texto  # el postulante sigue sabiendo que puede mandar el CV
    otra = sin_alta("quiero ver mis kilos", estado=Estado(IDENTIFICAR))
    assert otra.texto.startswith("No reconocí ese dato.") and PEDIR_DATO in otra.texto


def test_codigo_de_cuenta_vincula_y_muestra_el_menu_de_consulta():
    identificar = Identificador([PEREZ])
    respuesta = sin_alta("j80158", identificar=identificar)
    assert identificar.pedidos == [("cuenta", "J80158")]
    assert respuesta.accion == VINCULAR and respuesta.cuenta == PEREZ
    assert respuesta.estado == Estado(MENU, PEREZ.clientecuit)
    assert respuesta.opciones == ["Ver estadísticas", "Descargar reporte", "Comprobante de descarga",
                                  "Cambiar de cuenta", "Salir"]
    assert "Salir" in respuesta.texto


def test_cuit_con_varias_cuentas_pide_elegir_y_vincula_la_elegida():
    identificar = Identificador([ENAV, PEREZ])
    respuesta = sin_alta("20-22714958-3", identificar=identificar)
    assert identificar.pedidos == [("cuit", "20227149583")]
    assert "El CUIT *20227149583* está asociado a *2 cuentas*" in respuesta.texto
    assert respuesta.opciones == ["G03436 — ENAV S.A", "J80158 — PEREZ JUAN"]
    assert respuesta.estado.paso == ELEGIR_VINCULO
    assert respuesta.estado.candidatas == ("30500010912", "20227149583")
    elegida = sin_alta("2", estado=respuesta.estado, candidatas=[ENAV, PEREZ])
    assert elegida.accion == VINCULAR and elegida.cuenta == PEREZ


def test_patente_busca_la_cuenta_de_sus_descargas():
    identificar = Identificador([ENAV])
    assert sin_alta("Vct 917", identificar=identificar).cuenta == ENAV
    assert sin_alta("AB-123-CD", identificar=identificar).accion == VINCULAR
    assert identificar.pedidos == [("patente", "VCT917"), ("patente", "AB123CD")]


def test_cuit_mal_escrito_no_gasta_un_intento():
    identificar = Identificador([ENAV])
    respuesta = sin_alta("20227149584", identificar=identificar)
    assert "no es válido" in respuesta.texto and identificar.pedidos == []


def test_dato_que_no_existe_vuelve_a_pedir():
    respuesta = sin_alta("Z99999", identificar=Identificador([]))
    assert respuesta.texto.startswith("No encontré ninguna cuenta con la cuenta *Z99999*")
    assert respuesta.estado.paso == IDENTIFICAR and respuesta.accion is None


def test_pasado_el_tope_de_intentos_no_busca_mas():
    respuesta = sin_alta("Z99999", identificar=Identificador(bloqueado=True))
    assert respuesta.texto == DEMASIADOS_INTENTOS and respuesta.accion is None


# --- Vínculo abierto: sólo consulta ---------------------------------------------------------


def test_salir_desvincula():
    respuesta = abierta("Salir")
    assert respuesta.accion == DESVINCULAR and respuesta.texto == DESVINCULADA
    assert respuesta.estado.paso == IDENTIFICAR
    assert abierta("5").accion == DESVINCULAR  # «Salir» del menú, por número


def test_cambiar_de_cuenta_desvincula_y_pide_el_dato():
    respuesta = abierta("Cambiar de cuenta")
    assert respuesta.accion == DESVINCULAR and PEDIR_DATO in respuesta.texto


class TurnosQueNoSeUsan:
    def __getattr__(self, nombre):
        raise AssertionError(f"el vínculo abierto no puede usar turnos ({nombre})")


def test_vinculo_abierto_no_ofrece_uva_ni_turnos_ni_contactos():
    cuenta = Cuenta(PEREZ.clientecuit, PEREZ.codigo, PEREZ.titular, TODO)
    for texto in ("ofrecer uva", "mis turnos", "mis contactos", "quiero ofrecer"):
        respuesta = responder(texto, [cuenta], Estado(MENU, cuenta.clientecuit), HOY, sesion_abierta=True,
                              puede_pedir_turnos=True, puede_administrar=True, turnos=TurnosQueNoSeUsan())
        assert respuesta.accion is None and respuesta.estado.paso == MENU
        assert "Ofrecer uva" not in respuesta.opciones and "Mis contactos" not in respuesta.opciones
    # Tampoco desde un paso de oferta guardado de antes.
    respuesta = responder("1", [cuenta], Estado("oferta_sede", cuenta.clientecuit), HOY, sesion_abierta=True,
                          puede_pedir_turnos=True, turnos=TurnosQueNoSeUsan())
    assert respuesta.estado.paso == MENU


# --- Comprobante DDJJ -------------------------------------------------------------------------


def test_numero_de_ciu_en_el_menu_pide_ese_comprobante():
    for texto, ciu in (("17377", "17377"), ("CIU 0000017377", "0000017377"), ("N° 17377", "17377")):
        respuesta = abierta(texto)
        assert (respuesta.accion, respuesta.ciu, respuesta.cuenta) == (COMPROBANTE, ciu, PEREZ)
    # Los números del menú y un CUIT no son un CIU.
    assert abierta("2").accion is None
    assert abierta("20227149583").accion is None


def test_opcion_comprobante_pregunta_cual():
    pregunta = abierta("Comprobante de descarga")
    assert pregunta.estado.paso == COMPROBANTE and pregunta.opciones == ["Última descarga", "Volver"]
    ultima = abierta("1", estado=pregunta.estado)
    assert ultima.accion == COMPROBANTE and ultima.ciu is None
    por_numero = abierta("17377", estado=pregunta.estado)
    assert por_numero.ciu == "17377"
    assert abierta("Volver", estado=pregunta.estado).estado.paso == MENU
    assert "No entendí" in abierta("cualquiera", estado=pregunta.estado).texto


def test_los_numeros_dados_de_alta_tambien_piden_comprobantes():
    respuesta = responder("17377", [ENAV], Estado(MENU, ENAV.clientecuit), HOY)
    assert respuesta.accion == COMPROBANTE and respuesta.cuenta == ENAV
    sin_informes = responder("17377", [ENAV], Estado(MENU, ENAV.clientecuit), HOY,
                             puede_ver_informes=False)
    assert sin_informes.accion is None


def test_pdf_del_comprobante():
    comprobante = Comprobante("17377", datetime(2026, 2, 10, 9, 30), "media-agua", "J80158",
                              "PEREZ & HIJOS S.A.", "Malbec", 23_450, 23.5)
    assert nombre_comprobante(comprobante) == "DDJJ_CIU_0000017377_20260210.pdf"
    contenido = generar_comprobante(comprobante)
    assert contenido.startswith(b"%PDF-") and len(contenido) > 1000


# --- Ids de los botones ---------------------------------------------------------------------


def test_el_id_del_boton_vale_aunque_el_titulo_venga_recortado():
    respuesta = abierta("op:Comprobante de descarga")
    assert respuesta.estado.paso == COMPROBANTE


def test_ver_mas_repite_la_pregunta_desde_esa_opcion():
    muchas = [Cuenta(f"20-{i}", f"G{i:05d}", f"PRODUCTOR {i}") for i in range(12)]
    estado = Estado(ELEGIR_VINCULO, candidatas=tuple(c.clientecuit for c in muchas))
    respuesta = sin_alta("pag:9", estado=estado, candidatas=muchas)
    assert respuesta.desde == 9 and respuesta.accion is None and len(respuesta.opciones) == 12
    assert "No entendí" not in respuesta.texto
    elegida = sin_alta("op:G00010 — PRODUCTOR 10", estado=estado, candidatas=muchas)
    assert elegida.cuenta == muchas[10]


def test_meta_entrega_el_id_del_boton():
    def mensaje(tipo, cuerpo):
        return {"entry": [{"changes": [{"value": {"messages": [{
            "id": "wamid.1", "from": TELEFONO, "type": "interactive",
            "interactive": {"type": tipo, tipo: cuerpo}}]}}]}]}

    [boton] = extraer_mensajes(mensaje("button_reply", {"id": "op:Comprobante de descarga",
                                                        "title": "Comprobante de des…"}))
    assert boton.texto == "op:Comprobante de descarga"
    [pagina] = extraer_mensajes(mensaje("list_reply", {"id": "pag:9", "title": "Ver más…"}))
    assert pagina.texto == "pag:9"
    [ajeno] = extraer_mensajes(mensaje("button_reply", {"id": "otro", "title": "Sí"}))
    assert ajeno.texto == "Sí"


# --- Mensajes interactivos de Meta ------------------------------------------------------------


def _cliente(pedidos):
    def manejar(pedido):
        pedidos.append(json.loads(pedido.content))
        return httpx.Response(200, json={"messages": [{"id": f"wamid.{len(pedidos)}"}]})

    return ClienteMeta(ConfigMeta("TOKEN", "123"), httpx.Client(transport=httpx.MockTransport(manejar)))


def test_hasta_tres_opciones_van_como_botones():
    pedidos = []
    assert _cliente(pedidos).enviar_opciones(TELEFONO, "¿De qué período?",
                                             ["Cosecha 2026", "Últimos 3 meses", "Comprobante de descarga"]) == "wamid.1"
    [cuerpo] = pedidos
    interactivo = cuerpo["interactive"]
    assert cuerpo["type"] == "interactive" and interactivo["type"] == "button"
    assert interactivo["body"] == {"text": "¿De qué período?"}
    botones = interactivo["action"]["buttons"]
    assert [b["reply"]["title"] for b in botones] == ["Cosecha 2026", "Últimos 3 meses", "Comprobante de desc…"]
    assert all(len(b["reply"]["title"]) <= 20 for b in botones)
    assert botones[2]["reply"]["id"] == "op:Comprobante de descarga"


def test_de_cuatro_a_diez_van_como_lista_con_descripcion_si_no_entra():
    opciones = ["Ver estadísticas", "Descargar reporte", "Comprobante de descarga",
                "G03436 — FINCA LOS ALAMOS DEL ESTE S.A."]
    interactivo = cuerpo_opciones(TELEFONO, "Menú", opciones)["interactive"]
    assert interactivo["type"] == "list" and interactivo["action"]["button"] == "Ver opciones"
    filas = interactivo["action"]["sections"][0]["rows"]
    assert len(filas) == 4 and all(len(f["title"]) <= 24 for f in filas)
    assert "description" not in filas[0]
    assert filas[3]["description"] == "G03436 — FINCA LOS ALAMOS DEL ESTE S.A."
    assert all(len(f.get("description", "")) <= 72 for f in filas)


def test_mas_de_diez_muestra_nueve_y_ver_mas():
    opciones = [f"G{i:05d} — PRODUCTOR {i}" for i in range(12)]
    filas = cuerpo_opciones(TELEFONO, "Elegí", opciones)["interactive"]["action"]["sections"][0]["rows"]
    assert len(filas) == 10 and filas[-1]["id"] == "pag:9" and filas[-1]["title"] == "Ver más…"
    assert filas[-1]["description"] == "3 opciones más"
    siguientes = cuerpo_opciones(TELEFONO, "Elegí", opciones, desde=9)["interactive"]["action"]
    assert [f["id"] for f in siguientes["sections"][0]["rows"]] == [f"op:{o}" for o in opciones[9:]]


def test_texto_largo_sale_antes_y_la_pregunta_queda_como_cuerpo():
    pedidos = []
    largo = "Tus ofertas:\n" + "\n".join(f"• Malbec {i}" for i in range(150))
    _cliente(pedidos).enviar_opciones(TELEFONO, f"{largo}\n\n¿Qué querés consultar?", ["A", "B"])
    assert [p["type"] for p in pedidos] == ["text", "interactive"]
    assert pedidos[0]["text"]["body"] == largo
    assert pedidos[1]["interactive"]["body"]["text"] == "¿Qué querés consultar?"


# --- Worker -----------------------------------------------------------------------------------


class Salida:
    def __init__(self):
        self.enviados = []

    def enviar_texto(self, telefono, texto):
        self.enviados.append(("texto", texto))
        return "wamid-texto"

    def enviar_imagen(self, *args):
        self.enviados.append(("imagen", args))
        return "wamid-imagen"

    def enviar_documento(self, telefono, url, nombre, epigrafe=None):
        self.enviados.append(("documento", nombre, epigrafe))
        return "wamid-documento"


class SalidaMeta(Salida):
    def enviar_opciones(self, telefono, texto, opciones, desde=0):
        self.enviados.append(("opciones", texto, list(opciones), desde))
        return "wamid-opciones"


class Consultas:
    def __init__(self, hay=True):
        self.hay, self.pedidos = hay, []

    def entregas(self, *_):
        return []

    def comprobante(self, clientecuit, ciu, titular, codigo):
        self.pedidos.append((clientecuit, ciu))
        if not self.hay:
            return None
        return Comprobante(ciu or "17377", datetime(2026, 2, 10, 9, 30), "chimbas", codigo, titular,
                           "Malbec", 23_450, None)


class BotSinAlta:
    """Un número que no es productor ni personal."""

    def __init__(self, texto, vinculada=None, identificadas=(), estado=None, tipo="text"):
        self.texto, self.tipo = texto, tipo
        self.vinculada, self.identificar = vinculada, Identificador(identificadas)
        self._estado = estado or Estado()
        self.vinculos, self.desvinculos, self.consultas, self.estados = [], [], [], []
        self.cierres, self.archivos, self.cvs = [], [], []

    def tomar(self):
        media = "media-1" if self.tipo != "text" else None
        return [Pendiente(1, TELEFONO, self.texto, 0, self.tipo, media)]

    def respuestas_ultima_hora(self, _):
        return 0

    def cuentas(self, _):
        return []

    def vinculo(self, telefono):
        assert telefono == TELEFONO
        return self.vinculada

    def identificador(self, telefono):
        assert telefono == TELEFONO
        return self.identificar

    def cuentas_por_cuit(self, cuits):
        return [c for c in (ENAV, PEREZ) if c.clientecuit in cuits]

    def permisos(self, _):
        raise AssertionError("sin alta no hay permisos que leer")

    def turnos(self, _):
        raise AssertionError("el vínculo abierto no usa turnos")

    def estado_y_caducidad(self, _):
        return self._estado, False

    def guardar_estado(self, _, estado):
        self.estados.append(estado)

    def vincular(self, telefono, cuenta):
        self.vinculos.append((telefono, cuenta))

    def desvincular(self, telefono):
        self.desvinculos.append(telefono)

    def registrar_consulta(self, *args):
        self.consultas.append(args)

    def registrar_cv(self, telefono, nombre, contenido, tipo):
        self.cvs.append(nombre)
        return 1

    def limpiar_archivos(self):
        return 0

    def guardar_archivo(self, archivo, _):
        self.archivos.append(archivo)

    def cerrar(self, *args, **kwargs):
        self.cierres.append((args, kwargs))

    def reintentar(self, *args):
        raise AssertionError(f"no debería reintentar: {args}")


def _procesar(monkeypatch, bot, salida, consultas=None):
    monkeypatch.setenv("BOT_PUBLIC_BASE_URL", "https://juviar-bot.duckdns.org")
    monkeypatch.setattr("consulta_publica.bot.transporte.fecha_hoy", lambda: HOY)
    procesar_una_vez(bot, consultas or Consultas(), salida)


def test_al_identificarse_llega_el_comprobante_y_despues_el_menu_con_botones(monkeypatch):
    bot, salida, consultas = BotSinAlta("J80158", identificadas=[PEREZ]), SalidaMeta(), Consultas()
    _procesar(monkeypatch, bot, salida, consultas)
    assert bot.vinculos == [(TELEFONO, PEREZ)]
    assert consultas.pedidos == [(PEREZ.clientecuit, None)]
    assert [e[0] for e in salida.enviados] == ["documento", "opciones"]
    assert salida.enviados[0][1] == "DDJJ_CIU_0000017377_20260210.pdf"
    assert salida.enviados[1][2][-1] == "Salir"
    # Queda rastro en la bitácora, con el teléfono.
    assert bot.consultas == [(PEREZ.clientecuit, "whatsapp:vincular", 1, TELEFONO),
                             (PEREZ.clientecuit, "whatsapp:comprobante", 1, TELEFONO)]
    assert bot.cierres[0][0][1] == "respondido"


def test_sin_descargas_se_vincula_igual_y_llega_el_menu(monkeypatch):
    bot, salida = BotSinAlta("J80158", identificadas=[PEREZ]), SalidaMeta()
    _procesar(monkeypatch, bot, salida, Consultas(hay=False))
    assert bot.vinculos and [e[0] for e in salida.enviados] == ["opciones"]


def test_en_el_simulador_y_por_chattigo_el_menu_sigue_numerado(monkeypatch):
    bot, salida = BotSinAlta("hola"), Salida()
    _procesar(monkeypatch, bot, salida)
    assert salida.enviados == [("texto", PEDIR_DATO)]
    bot, salida = BotSinAlta("20227149583", identificadas=[ENAV, PEREZ]), Salida()
    _procesar(monkeypatch, bot, salida)
    assert "1 — G03436 — ENAV S.A" in salida.enviados[0][1]
    assert bot.estados[-1].candidatas == ("30500010912", "20227149583") and not bot.vinculos


def test_elegir_entre_las_candidatas_guardadas(monkeypatch):
    estado = Estado(ELEGIR_VINCULO, candidatas=(ENAV.clientecuit, PEREZ.clientecuit))
    bot, salida = BotSinAlta("op:G03436 — ENAV S.A", estado=estado), SalidaMeta()
    _procesar(monkeypatch, bot, salida)
    assert bot.vinculos == [(TELEFONO, ENAV)]


def test_vinculado_pide_comprobante_por_ciu_de_su_cuenta(monkeypatch):
    bot = BotSinAlta("0000017377", vinculada=PEREZ, estado=Estado(MENU, PEREZ.clientecuit))
    salida, consultas = SalidaMeta(), Consultas()
    _procesar(monkeypatch, bot, salida, consultas)
    assert consultas.pedidos == [(PEREZ.clientecuit, "0000017377")]
    assert salida.enviados[0][0] == "documento"
    assert bot.consultas == [(PEREZ.clientecuit, "whatsapp:comprobante", 1, TELEFONO)]


def test_ciu_que_no_es_de_la_cuenta_no_aparece(monkeypatch):
    bot = BotSinAlta("99999", vinculada=PEREZ, estado=Estado(MENU, PEREZ.clientecuit))
    salida = SalidaMeta()
    _procesar(monkeypatch, bot, salida, Consultas(hay=False))
    assert salida.enviados[0][0] == "texto" and "No encontré el comprobante N.º 99999" in salida.enviados[0][1]


def test_vinculado_no_ofrece_uva(monkeypatch):
    bot = BotSinAlta("ofrecer uva", vinculada=PEREZ, estado=Estado(MENU, PEREZ.clientecuit))
    salida = SalidaMeta()
    _procesar(monkeypatch, bot, salida)
    assert salida.enviados[0][0] == "opciones" and "Ofrecer uva" not in salida.enviados[0][2]


def test_vinculado_sale(monkeypatch):
    bot = BotSinAlta("salir", vinculada=PEREZ, estado=Estado(MENU, PEREZ.clientecuit))
    salida = SalidaMeta()
    _procesar(monkeypatch, bot, salida)
    assert bot.desvinculos == [TELEFONO] and salida.enviados == [("texto", DESVINCULADA)]


class SalidaConArchivo(Salida):
    def descargar_media(self, media_id, maximo=0):
        return b"%PDF-1.4 " + b"x" * 500, "application/pdf"


def test_sin_alta_un_archivo_sigue_siendo_un_cv(monkeypatch):
    bot, salida = BotSinAlta(None, tipo="document"), SalidaConArchivo()
    _procesar(monkeypatch, bot, salida)
    assert bot.cvs and not bot.vinculos and "CV" in salida.enviados[0][1]
