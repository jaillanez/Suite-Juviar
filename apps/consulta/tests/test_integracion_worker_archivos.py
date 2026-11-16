from datetime import date

import psycopg
from consulta_publica.api.archivos import configurar, router
from consulta_publica.bot.dialogo import (
    OFERTA_SEDE,
    OFERTA_VARIEDAD,
    PERIODO,
    Cuenta,
    Estado,
)
from consulta_publica.bot.repositorio import Pendiente
from consulta_publica.bot.turnos import Borrador
from consulta_publica.bot.worker import enviar_avisos, procesar_una_vez
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
        self.consultas = []
        self.falla = falla

    def variedades(self, clientecuit):
        if self.falla:
            raise self.falla
        self.consultas.append(clientecuit)
        return ["Cereza", "Malbec"]


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
        return Estado(OFERTA_SEDE, "20-1", None, Borrador()), False

    def guardar_estado(self, _, estado):
        self.estados.append(estado)

    def turnos(self, telefono):
        assert telefono == "5492640000000"
        return self._turnos

    def reintentar(self, *args):
        self.reintentos.append(args)


def test_la_oferta_elige_bodega_y_muestra_las_variedades_del_productor(monkeypatch):
    monkeypatch.setenv("BOT_PUBLIC_BASE_URL", "https://juviar-bot.duckdns.org")
    monkeypatch.setattr("consulta_publica.bot.transporte.fecha_hoy", lambda: date(2026, 3, 17))
    turnos = TurnosQueAnotan()
    bot, salida = BotConTurnos(turnos), Salida()
    procesar_una_vez(bot, Consultas(), salida)
    assert turnos.consultas == ["20-1"]
    assert bot.estados[-1].paso == OFERTA_VARIEDAD and bot.estados[-1].turno.sede == "chimbas"
    assert "1 — Cereza" in salida.textos[0]


def test_falla_de_la_base_en_el_dialogo_se_reintenta(monkeypatch):
    monkeypatch.setenv("BOT_PUBLIC_BASE_URL", "https://juviar-bot.duckdns.org")
    monkeypatch.setattr("consulta_publica.bot.transporte.fecha_hoy", lambda: date(2026, 3, 17))
    bot, salida = BotConTurnos(TurnosQueAnotan(falla=psycopg.OperationalError("caída"))), Salida()
    procesar_una_vez(bot, Consultas(), salida)
    assert len(bot.reintentos) == 1 and not salida.textos and not bot.estados


class BotQueNoGuardaSesion(BotConTurnos):
    def guardar_estado(self, _, estado):
        raise psycopg.OperationalError("no se pudo guardar")


def test_si_no_se_guarda_la_sesion_no_se_reintenta_el_mensaje(monkeypatch):
    # Reintentar después de que el diálogo respondió podría reservar dos veces el mismo turno.
    monkeypatch.setenv("BOT_PUBLIC_BASE_URL", "https://juviar-bot.duckdns.org")
    monkeypatch.setattr("consulta_publica.bot.transporte.fecha_hoy", lambda: date(2026, 3, 17))
    bot, salida = BotQueNoGuardaSesion(TurnosQueAnotan()), Salida()
    procesar_una_vez(bot, Consultas(), salida)
    assert bot.reintentos == [] and "1 — Cereza" in salida.textos[0]


class BotConPersonal(Bot):
    def personal(self, _):
        from consulta_publica.bot.repositorio import Personal

        return Personal("PEREZ, JUAN CARLOS", "ENAV", "mando_medio")

    def cuentas(self, _):
        raise AssertionError("al personal no se le buscan cuentas de productor")


def test_personal_recibe_saludo_con_nombre_y_no_entra_al_menu(monkeypatch):
    monkeypatch.setenv("BOT_PUBLIC_BASE_URL", "https://juviar-bot.duckdns.org")
    monkeypatch.setattr("consulta_publica.bot.transporte.fecha_hoy", lambda: date(2026, 3, 17))
    bot, salida = BotConPersonal(), Salida()
    assert procesar_una_vez(bot, Consultas(), salida) == 1
    assert salida.textos == ["Hola, Juan (Mando medio, ENAV).\nTodavía no hay consultas habilitadas para vos."]
    assert bot.cierres[0][0][1] == "respondido"


class BotConAvisos:
    def __init__(self):
        self.marcas = []

    def tomar_avisos(self):
        return [{"id": 1, "telefono": "5492640000000", "texto": "Te asignamos los días"},
                {"id": 2, "telefono": "5492641111111", "texto": "Otro"}]

    def marcar_aviso(self, id_, wamid, error):
        self.marcas.append((id_, wamid, error))


class SalidaQueFallaUnaVez(Salida):
    def enviar_texto(self, telefono, texto):
        if telefono.endswith("1111111"):
            raise OSError("sin red")
        return super().enviar_texto(telefono, texto)


def test_avisos_de_la_bodega_se_envian_y_se_marcan():
    bot, salida = BotConAvisos(), SalidaQueFallaUnaVez()
    assert enviar_avisos(bot, salida) == 2
    assert salida.textos == ["Te asignamos los días"]
    assert bot.marcas[0][0] == 1 and bot.marcas[0][2] is None
    assert bot.marcas[1] == (2, None, "sin red")


class BotQueNoMarca(BotConAvisos):
    def marcar_aviso(self, id_, wamid, error):
        raise psycopg.OperationalError("caída")


def test_si_no_se_puede_marcar_el_aviso_sigue_con_los_demas():
    salida = Salida()
    assert enviar_avisos(BotQueNoMarca(), salida) == 2
    assert salida.textos == ["Te asignamos los días", "Otro"]
