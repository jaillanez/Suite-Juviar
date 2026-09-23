from datetime import date

from consulta_publica.bot.dialogo import (
    CONTACTOS,
    CUENTA,
    ESTADISTICAS,
    MENU,
    NO_REGISTRADO,
    PERIODO,
    SIN_PERMISO_INFORMES,
    Cuenta,
    Estado,
    responder,
)

HOY = date(2026, 3, 17)
UNA = [Cuenta("20-1", "G03436", "RODRIGUEZ NESTOR FABIAN.")]
DOS = UNA + [Cuenta("20-2", "H09870", "BARASSI ANGELA MARIA")]


def r(texto, cuentas=UNA, estado=None, **kw):
    return responder(texto, cuentas, estado or Estado(), HOY, **kw)


def test_numero_no_registrado():
    assert r("hola", cuentas=[]).texto == NO_REGISTRADO


def test_solo_pedir_turnos_no_ve_informes():
    assert r("1", puede_ver_informes=False).texto == SIN_PERMISO_INFORMES


def test_saludo_con_una_cuenta_va_al_menu():
    respuesta = r("Hola")
    assert "RODRIGUEZ NESTOR FABIAN" in respuesta.texto
    assert respuesta.opciones[:2] == ["Ver estadísticas", "Descargar reporte"]
    assert "1 — Ver estadísticas" in respuesta.con_botones()


def test_con_dos_cuentas_pregunta_cual():
    respuesta = r("hola", cuentas=DOS)
    assert respuesta.estado.paso == CUENTA and len(respuesta.opciones) == 2
    assert "G03436" in respuesta.opciones[0]


def test_elegir_cuenta_por_numero():
    respuesta = r("2", cuentas=DOS, estado=Estado(CUENTA))
    assert respuesta.estado.cuenta == "20-2" and "BARASSI" in respuesta.texto


def test_estadisticas_pide_periodo():
    respuesta = r("1", estado=Estado(MENU, "20-1"))
    assert respuesta.estado.paso == PERIODO and respuesta.estado.pedido == ESTADISTICAS
    assert respuesta.opciones == ["Cosecha 2026", "Últimos 3 meses"]


def test_periodo_por_boton_dispara_la_accion():
    respuesta = r("1", estado=Estado(PERIODO, "20-1", ESTADISTICAS))
    assert respuesta.accion == ESTADISTICAS
    assert (respuesta.periodo.desde, respuesta.periodo.hasta) == (date(2025, 12, 1), date(2026, 11, 30))
    assert respuesta.cuenta.codigo == "G03436"


def test_periodo_escrito_a_mano():
    respuesta = r("marzo 2025", estado=Estado(PERIODO, "20-1", "reporte"))
    assert respuesta.accion == "reporte" and respuesta.periodo.desde == date(2025, 3, 1)


def test_periodo_que_no_se_entiende_vuelve_a_preguntar():
    respuesta = r("cualquier cosa", estado=Estado(PERIODO, "20-1", ESTADISTICAS))
    assert respuesta.accion is None and respuesta.estado.paso == PERIODO
    assert "No entendí" in respuesta.texto


def test_volver_desde_el_periodo():
    respuesta = r("volver", estado=Estado(PERIODO, "20-1", ESTADISTICAS))
    assert respuesta.estado.paso == MENU and respuesta.accion is None


def test_contactos_solo_para_administradores():
    assert r("3", estado=Estado(MENU, "20-1"), puede_administrar=True).accion == CONTACTOS
    sin_permiso = r("3", estado=Estado(MENU, "20-1"), puede_administrar=False)
    assert sin_permiso.accion is None and "administra" in sin_permiso.texto


def test_cambiar_de_cuenta_solo_con_varias():
    assert r("4", cuentas=DOS, estado=Estado(MENU, "20-1")).estado.paso == CUENTA
    assert r("4", estado=Estado(MENU, "20-1")).estado.paso == MENU   # con una sola, no existe


def test_tambien_entiende_las_palabras():
    assert r("ver estadisticas", estado=Estado(MENU, "20-1")).estado.pedido == ESTADISTICAS
    assert r("quiero el pdf", estado=Estado(MENU, "20-1")).estado.pedido == "reporte"
