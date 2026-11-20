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
from consulta_publica.bot.worker import (
    AYUDA_MANTENIMIENTO,
    AYUDA_PERSONAL,
    enviar_avisos,
    procesar_una_vez,
)
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
    # El saludo lista las tres cosas que el personal puede mandar (fase 5: antes sólo Mantenimiento).
    assert salida.textos == ["Hola, Juan (Mando medio, ENAV).\n" + AYUDA_PERSONAL]
    assert AYUDA_MANTENIMIENTO in AYUDA_PERSONAL and "certificado" in AYUDA_PERSONAL and "EPP" in AYUDA_PERSONAL
    assert bot.cierres[0][0][1] == "respondido"


class BotMantenimiento(BotConPersonal):
    def __init__(self, pendiente, falla=None):
        super().__init__()
        self.pendiente, self.falla, self.registrados = pendiente, falla, []

    def tomar(self):
        return [self.pendiente]

    def registrar_mantenimiento(self, telefono, texto, foto, tipo):
        if self.falla:
            raise ValueError(self.falla)
        self.registrados.append((telefono, texto, foto, tipo))
        return 7


class SalidaConFotos(Salida):
    def __init__(self, foto=None):
        super().__init__()
        self.foto = foto

    def descargar_media(self, media_id):
        if self.foto is None:
            raise OSError("sin red")
        return self.foto, "image/jpeg"


def _procesar(monkeypatch, bot, salida):
    monkeypatch.setenv("BOT_PUBLIC_BASE_URL", "https://juviar-bot.duckdns.org")
    monkeypatch.setattr("consulta_publica.bot.transporte.fecha_hoy", lambda: date(2026, 3, 17))
    procesar_una_vez(bot, Consultas(), salida)


def test_foto_del_personal_queda_para_mantenimiento(monkeypatch):
    foto = b"\xff\xd8" + b"0" * 5000
    bot = BotMantenimiento(Pendiente(1, "5492640000000", "BOM-0003 a taller", 0, "image", "MEDIA.1"))
    salida = SalidaConFotos(foto)
    _procesar(monkeypatch, bot, salida)
    assert bot.registrados == [("5492640000000", "BOM-0003 a taller", foto, "image/jpeg")]
    assert "N.º 7" in salida.textos[0]


def test_si_la_foto_no_baja_igual_se_registra_el_texto_y_se_avisa(monkeypatch):
    bot = BotMantenimiento(Pendiente(1, "5492640000000", "sale la soldadora", 0, "image", "MEDIA.1"))
    salida = SalidaConFotos(None)
    _procesar(monkeypatch, bot, salida)
    assert bot.registrados[0][2] is None and "mandala de nuevo" in salida.textos[0]


def test_texto_comun_del_personal_no_se_registra_y_la_base_puede_rechazar(monkeypatch):
    bot = BotMantenimiento(Pendiente(1, "5492640000000", "hola", 0))
    salida = Salida()
    _procesar(monkeypatch, bot, salida)
    assert bot.registrados == [] and AYUDA_MANTENIMIENTO in salida.textos[0]
    bot = BotMantenimiento(Pendiente(1, "5492640000000", "sale el taladro al taller", 0), falla="tope de mensajes por hora")
    salida = Salida()
    _procesar(monkeypatch, bot, salida)
    assert salida.textos == ["No se pudo registrar: tope de mensajes por hora."]


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
    assert enviar_avisos(bot, salida) == 1  # el que falló no cuenta
    assert salida.textos == ["Te asignamos los días"]
    assert bot.marcas[0][0] == 1 and bot.marcas[0][2] is None
    assert bot.marcas[1] == (2, None, "sin red")


class BotQueMarcaAlTercerIntento(BotConAvisos):
    def __init__(self):
        super().__init__()
        self.fallas = 0

    def marcar_aviso(self, id_, wamid, error):
        if id_ == 1 and self.fallas < 2:
            self.fallas += 1
            raise psycopg.OperationalError("caída")
        super().marcar_aviso(id_, wamid, error)


def test_si_no_se_puede_marcar_el_aviso_se_insiste_y_sigue_con_los_demas(monkeypatch):
    monkeypatch.setattr("consulta_publica.bot.worker.time.sleep", lambda _: None)
    bot, salida = BotQueMarcaAlTercerIntento(), Salida()
    assert enviar_avisos(bot, salida) == 2
    assert salida.textos == ["Te asignamos los días", "Otro"]
    assert [m[0] for m in bot.marcas] == [1, 2] and bot.fallas == 2


class BotQueNuncaMarca(BotConAvisos):
    def __init__(self):
        super().__init__()
        self.llamadas = []

    def marcar_aviso(self, id_, wamid, error):
        self.llamadas.append(id_)
        raise psycopg.OperationalError("caída")


def test_marcar_se_insiste_solo_si_salio_y_sin_esperar_despues_del_ultimo(monkeypatch):
    esperas = []
    monkeypatch.setattr("consulta_publica.bot.worker.time.sleep", esperas.append)
    bot = BotQueNuncaMarca()
    assert enviar_avisos(bot, SalidaQueFallaUnaVez()) == 1
    assert bot.llamadas == [1, 1, 1, 2]   # el que falló al enviar se anota una sola vez
    assert esperas == [0.5, 1.0]


class SalidaQueFalla(Salida):
    def enviar_texto(self, telefono, texto):
        raise OSError("sin red")


def test_si_falla_la_respuesta_lo_registrado_no_se_reintenta(monkeypatch):
    bot = BotMantenimiento(Pendiente(1, "5492640000000", "sale el taladro al taller", 0))
    bot.reintentos = []
    bot.reintentar = lambda *a: bot.reintentos.append(a)
    _procesar(monkeypatch, bot, SalidaQueFalla())
    assert len(bot.registrados) == 1 and bot.reintentos == []
    assert bot.cierres[0][0][1] == "error"
