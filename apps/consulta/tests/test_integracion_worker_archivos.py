from datetime import date

from consulta_publica.api.archivos import configurar, router
from consulta_publica.bot.dialogo import PERIODO, Cuenta, Estado
from consulta_publica.bot.repositorio import Pendiente
from consulta_publica.bot.worker import procesar_una_vez
from fastapi import FastAPI
from fastapi.testclient import TestClient


class Salida:
    def __init__(self):
        self.textos = []
        self.medios = []

    def enviar_texto(self, telefono, texto):
        self.textos.append(texto)
        return "wamid-texto"

    def enviar_imagen(self, *args):
        self.medios.append(args)
        return "wamid-imagen"

    def enviar_documento(self, *args):
        self.medios.append(args)
        return "wamid-documento"


class Consultas:
    def entregas(self, *_):
        return []


class Bot:
    def __init__(self, caducada=False):
        self.caducada = caducada
        self.archivos = []
        self.cierres = []

    def tomar(self):
        return [Pendiente(1, "5492640000000", "1", 0)]

    def respuestas_ultima_hora(self, _):
        return 0

    def cuentas(self, _):
        return [Cuenta("20-1", "G00001", "PRODUCTOR PRUEBA")]

    def permisos(self, _):
        return {"ver_informes"}

    def estado_y_caducidad(self, _):
        return Estado(PERIODO, "20-1", "estadisticas"), self.caducada

    def guardar_estado(self, *_):
        pass

    def limpiar_archivos(self):
        return 0

    def guardar_archivo(self, archivo, _):
        self.archivos.append(archivo)

    def cerrar(self, *args, **kwargs):
        self.cierres.append((args, kwargs))

    def reintentar(self, *_):
        raise AssertionError("no debería reintentar")

    def registrar_consulta(self, *_):
        pass


def test_periodo_sin_entregas_no_crea_archivo(monkeypatch):
    monkeypatch.setenv("BOT_PUBLIC_BASE_URL", "https://juviar-bot.duckdns.org")
    monkeypatch.setattr("consulta_publica.bot.transporte.fecha_hoy", lambda: date(2026, 3, 17))
    bot, salida = Bot(), Salida()
    assert procesar_una_vez(bot, Consultas(), salida) == 1
    assert salida.textos == ["No hay entregas en ese período."]
    assert not salida.medios and not bot.archivos


def test_sesion_caducada_vuelve_al_menu(monkeypatch):
    monkeypatch.setenv("BOT_PUBLIC_BASE_URL", "https://juviar-bot.duckdns.org")
    monkeypatch.setattr("consulta_publica.bot.transporte.fecha_hoy", lambda: date(2026, 3, 17))
    salida = Salida()
    procesar_una_vez(Bot(caducada=True), Consultas(), salida)
    assert "Pasó un rato" in salida.textos[0]
    assert "¿Qué querés consultar?" in salida.textos[0]


class ArchivosVencidos:
    def leer(self, _):
        return None


def test_archivo_vencido_devuelve_404():
    configurar(ArchivosVencidos())
    app = FastAPI()
    app.include_router(router)
    respuesta = TestClient(app).get("/archivos/" + "a" * 43 + ".pdf")
    assert respuesta.status_code == 404
