from datetime import date, datetime

import psycopg
from consulta_publica.api.archivos import configurar, router
from consulta_publica.bot.conversacion import ZONA
from consulta_publica.bot.dialogo import PERIODO, TURNO_DIA, TURNO_SEDE, Cuenta, Estado
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


class TurnosQueAnotan:
    def __init__(self, falla=None):
        self.desde = []
        self.falla = falla

    def libres(self, sede, desde, hasta):
        if self.falla:
            raise self.falla
        self.desde.append(desde)
        return {desde: 150_000}


class BotConTurnos(Bot):
    def __init__(self, turnos):
        super().__init__()
        self._turnos = turnos
        self.reintentos = []
        self.estados = []

    def cuentas(self, _):
        return [Cuenta("20-1", "G00001", "PRODUCTOR PRUEBA", frozenset({"pedir_turnos"}))]

    def permisos(self, _):
        return {"pedir_turnos"}

    def estado_y_caducidad(self, _):
        return Estado(TURNO_SEDE, "20-1"), False

    def guardar_estado(self, _, estado):
        self.estados.append(estado)

    def turnos(self, telefono):
        assert telefono == "5492640000000"
        return self._turnos

    def reintentar(self, *args):
        self.reintentos.append(args)


def test_turnos_usan_la_fecha_real_aunque_haya_fecha_simulada(monkeypatch):
    monkeypatch.setenv("BOT_PUBLIC_BASE_URL", "https://juviar-bot.duckdns.org")
    monkeypatch.setattr("consulta_publica.bot.transporte.fecha_hoy", lambda: date(2026, 3, 17))
    turnos = TurnosQueAnotan()
    bot, salida = BotConTurnos(turnos), Salida()
    procesar_una_vez(bot, Consultas(), salida)
    assert turnos.desde == [datetime.now(ZONA).date()]
    assert bot.estados[-1].paso == TURNO_DIA and bot.estados[-1].turno.sede == "chimbas"
    assert "— 150 t libres" in salida.textos[0]


def test_falla_de_la_base_en_el_dialogo_se_reintenta(monkeypatch):
    monkeypatch.setenv("BOT_PUBLIC_BASE_URL", "https://juviar-bot.duckdns.org")
    monkeypatch.setattr("consulta_publica.bot.transporte.fecha_hoy", lambda: date(2026, 3, 17))
    bot, salida = BotConTurnos(TurnosQueAnotan(falla=psycopg.OperationalError("caída"))), Salida()
    procesar_una_vez(bot, Consultas(), salida)
    assert len(bot.reintentos) == 1 and not salida.textos and not bot.estados
