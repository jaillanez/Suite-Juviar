"""Fase 5: RRHH por WhatsApp en el bot (CV, certificados, EPP, confirmación y aviso del micro)."""

from datetime import date

from consulta_publica.bot.dialogo import NO_REGISTRADO, Estado
from consulta_publica.bot.meta import extraer_mensajes
from consulta_publica.bot.repositorio import Pendiente, Personal
from consulta_publica.bot.worker import (
    CONFIRMADO,
    CORRECCION_RECIBIDA,
    CV_RECIBIDO,
    FORMATO_NO_ADMITIDO,
    MAXIMO_ARCHIVO,
    PEDIR_CERTIFICADO,
    PEDIR_CORRECCION,
    PEDIR_PALABRA,
    destino_personal,
    enviar_avisos_personal,
    procesar_una_vez,
    texto_aviso_micro,
)

TELEFONO = "5492640000000"
PDF = b"%PDF-1.4\n" + b"0" * 1000
JPG = b"\xff\xd8\xff\xe0" + b"0" * 5000


def _payload(mensaje: dict) -> dict:
    return {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "N1"},
                                              "messages": [{"id": "wamid.1", "from": TELEFONO, **mensaje}]}}]}]}


# --- meta.py: documentos ------------------------------------------------------------------

def test_documento_pdf_trae_id_nombre_y_tipo():
    [m] = extraer_mensajes(_payload({"type": "document", "document": {
        "id": "MEDIA.9", "filename": "../CV Juan Pérez<script>.pdf", "mime_type": "application/pdf",
        "caption": "mi cv"}}))
    assert (m.media_id, m.media_tipo, m.texto) == ("MEDIA.9", "application/pdf", "mi cv")
    assert m.media_nombre == "..CV Juan Pérezscript.pdf"  # sin barras ni signos raros


def test_documento_de_tipo_no_admitido_no_se_baja():
    [m] = extraer_mensajes(_payload({"type": "document", "document": {
        "id": "MEDIA.9", "filename": "cv.docx",
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}}))
    assert m.media_id is None and m.tipo == "document"


def test_foto_conserva_el_comportamiento_y_suma_el_tipo():
    [m] = extraer_mensajes(_payload({"type": "image", "image": {"id": "MEDIA.1", "caption": "BOM-0003"}}))
    assert (m.media_id, m.media_tipo, m.media_nombre, m.texto) == ("MEDIA.1", "image/jpeg", None, "BOM-0003")
    [m] = extraer_mensajes(_payload({"type": "image", "image": {"id": "MEDIA.1", "mime_type": "image/gif"}}))
    assert m.media_id is None


# --- Fakes ----------------------------------------------------------------------------------

class Salida:
    def __init__(self, archivo=None):
        self.textos, self.archivo, self.maximos = [], archivo, []

    def enviar_texto(self, telefono, texto):
        self.textos.append(texto)
        return "wamid-texto"

    def descargar_media(self, media_id, maximo=3_000_000):
        self.maximos.append(maximo)
        if self.archivo is None:
            raise OSError("sin red")
        return self.archivo, "application/pdf"


class Consultas:
    def entregas(self, *_):
        return []


class Bot:
    def __init__(self, pendiente, personal=True, confirmacion=None):
        self.pendiente, self.es_personal, self.estado_confirmacion = pendiente, personal, confirmacion
        self.rrhh, self.mantenimiento, self.cvs, self.respuestas, self.cierres = [], [], [], [], []

    def tomar(self):
        return [self.pendiente]

    def respuestas_ultima_hora(self, _):
        return 0

    def personal(self, _):
        return Personal("PEREZ, JUAN", "ENAV", "personal") if self.es_personal else None

    def cuentas(self, _):
        assert not self.es_personal
        return []

    def permisos(self, _):
        return set()

    def estado_y_caducidad(self, _):
        return Estado(), False

    def guardar_estado(self, *_):
        pass

    def limpiar_archivos(self):
        return 0

    def registrar_rrhh(self, telefono, tipo, texto, archivo, archivo_tipo, nombre):
        self.rrhh.append((tipo, texto, archivo, archivo_tipo, nombre))
        return 11

    def registrar_mantenimiento(self, telefono, texto, foto, tipo):
        self.mantenimiento.append((texto, foto))
        return 7

    def registrar_cv(self, telefono, nombre, contenido, tipo):
        self.cvs.append((telefono, nombre, contenido, tipo))
        return 3

    def confirmacion_pendiente(self, _):
        return self.estado_confirmacion

    def responder_certificado(self, telefono, respuesta, correccion=None):
        self.respuestas.append((respuesta, correccion))
        nuevo = {("esperando", "si"): "confirmado", ("esperando", "no"): "corrigiendo",
                 ("corrigiendo", "correccion"): "no_coincide"}.get((self.estado_confirmacion, respuesta))
        self.estado_confirmacion = nuevo if nuevo == "corrigiendo" else None
        return nuevo

    def cerrar(self, *args, **kwargs):
        self.cierres.append((args, kwargs))

    def reintentar(self, *_):
        raise AssertionError("no debería reintentar")


def _procesar(monkeypatch, bot, salida):
    monkeypatch.setenv("BOT_PUBLIC_BASE_URL", "https://juviar-bot.duckdns.org")
    monkeypatch.setattr("consulta_publica.bot.transporte.fecha_hoy", lambda: date(2026, 11, 20))
    procesar_una_vez(bot, Consultas(), salida)
    return salida.textos


# --- Ruteo de los mensajes del personal ----------------------------------------------------

def test_palabras_deciden_a_donde_va():
    casos = {
        ("certificado del médico", "document"): "certificado",
        ("reposo 3 días", "image"): "certificado",
        ("EPP: necesito guantes", "text"): "epp",
        ("se me rompieron los botines", "image"): "epp",
        ("BOM-0003 sale a taller", "image"): "mantenimiento",
        ("", "image"): "sin_palabra",
        ("hola", "text"): "saludo",
    }
    for (texto, tipo), esperado in casos.items():
        pendiente = Pendiente(1, TELEFONO, texto, 0, tipo, "MEDIA.1" if tipo != "text" else None)
        assert destino_personal(pendiente) == esperado, texto


def test_certificado_con_pdf_queda_para_rrhh(monkeypatch):
    bot = Bot(Pendiente(1, TELEFONO, "certificado médico", 0, "document", "MEDIA.1", "cert.pdf",
                        "application/pdf"))
    salida = Salida(PDF)
    textos = _procesar(monkeypatch, bot, salida)
    assert bot.rrhh == [("certificado", "certificado médico", PDF, "application/pdf", "cert.pdf")]
    assert "N.º 11" in textos[0] and "revisión de RRHH" in textos[0]
    assert salida.maximos == [MAXIMO_ARCHIVO] and not bot.mantenimiento


def test_el_tipo_sale_de_los_bytes_y_lo_que_no_es_pdf_ni_foto_se_rechaza(monkeypatch):
    bot = Bot(Pendiente(1, TELEFONO, "certificado", 0, "document", "MEDIA.1", None, "application/pdf"))
    _procesar(monkeypatch, bot, Salida(JPG))
    assert bot.rrhh[0][3] == "image/jpeg" and bot.rrhh[0][4] == "certificado.jpg"
    bot = Bot(Pendiente(1, TELEFONO, "certificado", 0, "document", "MEDIA.1", None, "application/pdf"))
    textos = _procesar(monkeypatch, bot, Salida(b"MZ" + b"0" * 5000))
    assert bot.rrhh == [] and FORMATO_NO_ADMITIDO in textos[0] and PEDIR_CERTIFICADO in textos[0]


def test_certificado_sin_archivo_pide_la_foto(monkeypatch):
    bot = Bot(Pendiente(1, TELEFONO, "mañana llevo el certificado", 0))
    textos = _procesar(monkeypatch, bot, Salida())
    assert bot.rrhh == [] and textos == [PEDIR_CERTIFICADO]


def test_pedido_de_epp_con_texto_solo_o_con_foto(monkeypatch):
    bot = Bot(Pendiente(1, TELEFONO, "EPP: guantes talle 9", 0))
    textos = _procesar(monkeypatch, bot, Salida())
    assert bot.rrhh == [("epp", "EPP: guantes talle 9", None, None, None)] and "pedido de EPP" in textos[0]
    bot = Bot(Pendiente(1, TELEFONO, "casco roto", 0, "image", "MEDIA.1", None, "image/jpeg"))
    _procesar(monkeypatch, bot, Salida(JPG))
    assert bot.rrhh[0][:4] == ("epp", "casco roto", JPG, "image/jpeg")


def test_foto_sin_palabra_ya_no_va_a_mantenimiento(monkeypatch):
    """Antes una foto sola iba a Mantenimiento; ahora se pide para qué es."""
    bot = Bot(Pendiente(1, TELEFONO, None, 0, "image", "MEDIA.1", None, "image/jpeg"))
    textos = _procesar(monkeypatch, bot, Salida(JPG))
    assert textos == [PEDIR_PALABRA] and not bot.mantenimiento and not bot.rrhh


def test_mantenimiento_sigue_igual(monkeypatch):
    bot = Bot(Pendiente(1, TELEFONO, "sale la amoladora al taller", 0))
    textos = _procesar(monkeypatch, bot, Salida())
    assert bot.mantenimiento == [("sale la amoladora al taller", None)] and "N.º 7" in textos[0]


# --- CV desde un número desconocido ----------------------------------------------------

def test_numero_desconocido_con_pdf_es_un_cv(monkeypatch):
    bot = Bot(Pendiente(1, "5492645555555", None, 0, "document", "MEDIA.1", "cv.pdf", "application/pdf"),
              personal=False)
    textos = _procesar(monkeypatch, bot, Salida(PDF))
    assert bot.cvs == [("5492645555555", "cv.pdf", PDF, "application/pdf")] and textos == [CV_RECIBIDO]
    assert bot.cierres[0][0][1] == "respondido"


def test_numero_desconocido_con_foto_sin_nombre(monkeypatch):
    bot = Bot(Pendiente(1, "5492645555555", None, 0, "image", "MEDIA.1", None, "image/jpeg"), personal=False)
    _procesar(monkeypatch, bot, Salida(JPG))
    assert bot.cvs[0][1] == "cv-whatsapp.jpg"


def test_numero_desconocido_con_texto_recibe_no_registrado_con_la_ayuda_del_cv(monkeypatch):
    bot = Bot(Pendiente(1, "5492645555555", "hola", 0), personal=False)
    textos = _procesar(monkeypatch, bot, Salida())
    assert textos == [NO_REGISTRADO] and "CV en PDF o una foto" in NO_REGISTRADO and not bot.cvs


# --- Confirmación del certificado ------------------------------------------------------

def test_respuesta_1_confirma(monkeypatch):
    bot = Bot(Pendiente(1, TELEFONO, "1", 0), confirmacion="esperando")
    assert _procesar(monkeypatch, bot, Salida()) == [CONFIRMADO]
    assert bot.respuestas == [("si", None)]


def test_respuesta_2_y_despues_la_correccion(monkeypatch):
    bot = Bot(Pendiente(1, TELEFONO, "2", 0), confirmacion="esperando")
    assert _procesar(monkeypatch, bot, Salida()) == [PEDIR_CORRECCION]
    bot.pendiente = Pendiente(2, TELEFONO, "son 5 días, no 3", 0)
    assert _procesar(monkeypatch, bot, Salida()) == [CORRECCION_RECIBIDA]
    assert bot.respuestas == [("no", None), ("correccion", "son 5 días, no 3")]
    assert not bot.rrhh  # la corrección no se toma como un mensaje nuevo para RRHH


def test_mientras_espera_otro_mensaje_sigue_su_camino(monkeypatch):
    bot = Bot(Pendiente(1, TELEFONO, "EPP: botines 42", 0), confirmacion="esperando")
    _procesar(monkeypatch, bot, Salida())
    assert bot.respuestas == [] and bot.rrhh[0][0] == "epp"


def test_sin_nada_esperando_un_1_es_un_saludo(monkeypatch):
    bot = Bot(Pendiente(1, TELEFONO, "1", 0), confirmacion=None)
    textos = _procesar(monkeypatch, bot, Salida())
    assert textos[0].startswith("Hola, Juan") and bot.respuestas == []


# --- Cola de mensajes al personal ----------------------------------------------------------

class BotConCola:
    def __init__(self):
        self.marcas = []

    def tomar_avisos_personal(self):
        return [{"id": 1, "telefono": TELEFONO, "tipo": "micro", "recorrido": "Rawson", "texto": None},
                {"id": 2, "telefono": TELEFONO, "tipo": "certificado", "recorrido": None,
                 "texto": "Leímos tu certificado médico:\n• Días: 3"}]

    def marcar_aviso_personal(self, id_, wamid, error):
        self.marcas.append((id_, wamid, error))


def test_aviso_del_micro_y_lectura_del_certificado_salen_y_se_marcan():
    bot, salida = BotConCola(), Salida()
    assert enviar_avisos_personal(bot, salida) == 2
    assert salida.textos == [texto_aviso_micro("Rawson"), "Leímos tu certificado médico:\n• Días: 3"]
    assert "Rawson" in salida.textos[0]
    assert [m[0] for m in bot.marcas] == [1, 2] and all(m[2] is None for m in bot.marcas)
