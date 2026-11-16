from datetime import date

import pytest
from consulta_publica.bot.dialogo import (
    MENU,
    OFERTA_CONFIRMAR,
    OFERTA_CUENTA,
    OFERTA_KG,
    OFERTA_ORGANICA,
    OFERTA_SEDE,
    OFERTA_VARIEDAD,
    SIN_PERMISO_INFORMES,
    Cuenta,
    Estado,
    responder,
)
from consulta_publica.bot.turnos import (
    Borrador,
    OfertaRechazada,
    OfertaVigente,
    TurnoVigente,
    kilos_escritos,
    motivo_en_palabras,
)

ESTADISTICAS_FECHA = date(2026, 3, 17)        # BOT_FECHA_SIMULADA
HOY = date(2026, 11, 16)                      # fecha real (lunes)
TODO = frozenset({"ver_informes", "pedir_turnos", "administrar_contactos"})
JUAN = Cuenta("20-1", "G03436", "QUIROGA JUAN CARLOS.", TODO)
FINCA = Cuenta("30-7", "F001", "FINCA LOS ALAMOS SA", frozenset({"pedir_turnos"}))
SOLO_INFORMES = Cuenta("20-9", "H09870", "BARASSI ANGELA MARIA", frozenset({"ver_informes"}))


class TurnosFalsos:
    def __init__(self, organico=False, variedades=("Cereza", "Malbec", "Pedro Gimenez"),
                 rechazo=None, ofertas=(), proximos=()):
        self.organico = organico
        self.lista_variedades = list(variedades)
        self.rechazo = rechazo
        self.lista_ofertas = list(ofertas)
        self.lista_proximos = list(proximos)
        self.enviadas = []
        self.consultas = []

    def tiene_organico(self, clientecuit, fecha):
        assert fecha == HOY
        return self.organico

    def variedades(self, clientecuit):
        return self.lista_variedades

    def ofrecer(self, pedido, clientecuit, codigo, sede, variedad, kg, organica):
        self.enviadas.append((pedido, clientecuit, codigo, sede, variedad, kg, organica))
        if self.rechazo:
            raise OfertaRechazada(self.rechazo)
        return OfertaVigente(len(self.enviadas), sede, clientecuit, codigo, variedad, kg, "pendiente")

    def ofertas(self, clientecuits):
        self.consultas.append(("ofertas", clientecuits))
        return self.lista_ofertas

    def proximos(self, clientecuits, desde):
        self.consultas.append(("proximos", clientecuits, desde))
        return self.lista_proximos


def r(texto, estado=None, cuentas=(JUAN,), turnos=None, informes=True, **kw):
    return responder(
        texto,
        list(cuentas),
        estado or Estado(MENU, cuentas[0].clientecuit),
        ESTADISTICAS_FECHA,
        puede_ver_informes=informes,
        puede_pedir_turnos=True,
        turnos=turnos if turnos is not None else TurnosFalsos(),
        hoy_turnos=HOY,
        **kw,
    )


def en_paso(paso, cuenta=JUAN, **borrador):
    return Estado(paso, cuenta.clientecuit, None, Borrador(**borrador))


# --- Menú ---------------------------------------------------------------------------


def test_menu_muestra_ofrecer_uva_y_mis_turnos():
    respuesta = r("hola")
    assert respuesta.opciones == [
        "Ver estadísticas", "Descargar reporte", "Ofrecer uva", "Mis turnos", "Mis contactos",
    ]


def test_sin_tarea_pedir_turnos_no_hay_oferta():
    respuesta = r("hola", cuentas=(SOLO_INFORMES,))
    assert "Ofrecer uva" not in respuesta.opciones
    assert r("ofrecer", cuentas=(SOLO_INFORMES,)).estado.paso == MENU


def test_sin_repositorio_de_turnos_el_menu_queda_como_antes():
    respuesta = responder("hola", [JUAN], Estado(), ESTADISTICAS_FECHA, puede_pedir_turnos=True)
    assert "Ofrecer uva" not in respuesta.opciones


def test_numero_que_solo_ofrece_ve_su_menu():
    respuesta = r("hola", cuentas=(FINCA,), informes=False)
    assert respuesta.opciones == ["Ofrecer uva", "Mis turnos", "Mis contactos"]
    pide_informe = r("ver estadisticas", cuentas=(FINCA,), informes=False)
    assert pide_informe.estado.paso == MENU and SIN_PERMISO_INFORMES in pide_informe.texto


def test_sin_ningun_permiso_sigue_el_aviso():
    assert r("hola", cuentas=(SOLO_INFORMES,), informes=False).texto == SIN_PERMISO_INFORMES


def test_una_sesion_del_pedido_por_dia_vuelve_al_menu():
    respuesta = r("3", estado=Estado("turno_dia", "20-1"))
    assert respuesta.estado.paso == MENU


# --- Cuenta y bodega ----------------------------------------------------------------


def test_ofrecer_con_la_cuenta_del_menu_va_directo_a_la_bodega():
    respuesta = r("3")
    assert respuesta.estado.paso == OFERTA_SEDE and respuesta.estado.cuenta == "20-1"
    assert respuesta.opciones == ["Chimbas", "Lavalle", "Media Agua"]
    assert "QUIROGA JUAN CARLOS (G03436)" in respuesta.texto and "toda la temporada" in respuesta.texto


def test_varias_cuentas_que_no_pueden_ofrecer_desde_el_menu_pregunta_cual():
    otra = Cuenta("30-8", "F002", "VIÑAS DEL SUR", frozenset({"pedir_turnos"}))
    cuentas = (SOLO_INFORMES, FINCA, otra)
    respuesta = r("ofrecer uva", cuentas=cuentas)
    assert respuesta.estado.paso == OFERTA_CUENTA
    assert respuesta.opciones == ["FINCA LOS ALAMOS SA (F001)", "VIÑAS DEL SUR (F002)"]
    elegida = r("2", estado=respuesta.estado, cuentas=cuentas)
    assert elegida.estado.paso == OFERTA_SEDE and elegida.estado.cuenta == "30-8"


def test_una_sola_cuenta_habilitada_se_usa_sin_preguntar():
    respuesta = r("ofrecer uva", cuentas=(SOLO_INFORMES, FINCA))
    assert respuesta.estado.paso == OFERTA_SEDE and respuesta.estado.cuenta == "30-7"


@pytest.mark.parametrize(("texto", "sede"), [("2", "lavalle"), ("media agua", "media-agua")])
def test_elegir_bodega_por_numero_o_nombre(texto, sede):
    respuesta = r(texto, estado=en_paso(OFERTA_SEDE))
    assert respuesta.estado.paso == OFERTA_VARIEDAD and respuesta.estado.turno.sede == sede


def test_bodega_que_no_existe():
    respuesta = r("san martin", estado=en_paso(OFERTA_SEDE))
    assert respuesta.estado.paso == OFERTA_SEDE and "No entendí la bodega" in respuesta.texto


# --- Variedades y kilos ----------------------------------------------------------------


def test_muestra_las_variedades_que_entrego_y_deja_escribir_otra():
    respuesta = r("1", estado=en_paso(OFERTA_SEDE))
    assert respuesta.opciones == ["Cereza", "Malbec", "Pedro Gimenez"]
    assert "escribí el nombre" in respuesta.texto
    escrita = r("torrontés riojano", estado=respuesta.estado)
    assert escrita.estado.paso == OFERTA_KG and escrita.estado.turno.variedad == "Torrontés riojano"


def test_pide_los_kilos_de_toda_la_temporada():
    respuesta = r("2", estado=en_paso(OFERTA_VARIEDAD, sede="chimbas", opciones=("Cereza", "Malbec")))
    assert respuesta.estado.paso == OFERTA_KG and "Malbec" in respuesta.texto
    assert "toda la temporada" in respuesta.texto


@pytest.mark.parametrize("texto", ["mucho", "500", "999"])
def test_kilos_invalidos(texto):
    respuesta = r(texto, estado=en_paso(OFERTA_KG, sede="chimbas", variedad="Malbec"))
    assert respuesta.estado.paso == OFERTA_KG and "No me cerró" in respuesta.texto


def test_varias_variedades_y_listo():
    estado = en_paso(OFERTA_KG, sede="chimbas", variedad="Cereza")
    primera = r("80 t", estado=estado)
    assert primera.estado.paso == OFERTA_VARIEDAD
    assert primera.estado.turno.lineas == (("Cereza", 80_000),)
    # Ya no ofrece la que anotó, y aparece la opción para terminar.
    assert primera.opciones == ["Malbec", "Pedro Gimenez", "Listo, no hay más"]
    malbec = r("1", estado=primera.estado)
    segunda = r("40.000", estado=malbec.estado)
    assert segunda.estado.turno.lineas == (("Cereza", 80_000), ("Malbec", 40_000))
    listo = r("2", estado=segunda.estado)
    assert listo.estado.paso == OFERTA_CONFIRMAR
    assert "• Cereza: 80.000 kg" in listo.texto and "Total: 120.000 kg" in listo.texto
    assert "orgánica" not in listo.texto


def test_corregir_los_kilos_de_una_variedad_no_la_duplica():
    estado = en_paso(OFERTA_KG, sede="chimbas", variedad="cereza", lineas=(("Cereza", 80_000),))
    respuesta = r("70000", estado=estado)
    assert respuesta.estado.turno.lineas == (("cereza", 70_000),)


def test_listo_sin_ninguna_variedad_vuelve_a_preguntar():
    respuesta = r("listo", estado=en_paso(OFERTA_VARIEDAD, sede="chimbas"))
    assert respuesta.estado.paso == OFERTA_VARIEDAD and "Todavía no anotaste" in respuesta.texto


def test_con_certificado_pregunta_si_es_organica():
    estado = en_paso(OFERTA_VARIEDAD, sede="chimbas", lineas=(("Cereza", 80_000),), opciones=())
    respuesta = r("listo", estado=estado, turnos=TurnosFalsos(organico=True))
    assert respuesta.estado.paso == OFERTA_ORGANICA
    si = r("1", estado=respuesta.estado, turnos=TurnosFalsos(organico=True))
    assert si.estado.paso == OFERTA_CONFIRMAR and "Uva orgánica: sí" in si.texto


def test_interpretar_kilos():
    assert kilos_escritos("80.000") == 80_000
    assert kilos_escritos("80 t") == 80_000
    assert kilos_escritos("12,5 toneladas") == 12_500
    assert kilos_escritos("400000 kg") == 400_000
    assert kilos_escritos("mucho") is None


# --- Confirmar ------------------------------------------------------------------------


def _listo(**extra):
    datos = {"pedido": "p-1", "sede": "lavalle", "lineas": (("Cereza", 80_000), ("Malbec", 40_000))}
    return en_paso(OFERTA_CONFIRMAR, **{**datos, **extra})


def test_confirmar_envia_cada_variedad_con_el_mismo_pedido():
    turnos = TurnosFalsos()
    respuesta = r("1", estado=_listo(), turnos=turnos)
    assert turnos.enviadas == [
        ("p-1", "20-1", "G03436", "lavalle", "Cereza", 80_000, False),
        ("p-1", "20-1", "G03436", "lavalle", "Malbec", 40_000, False),
    ]
    assert respuesta.estado.paso == MENU
    assert "120.000 kg para Lavalle" in respuesta.texto and "te va a avisar" in respuesta.texto


def test_cancelar_no_envia():
    turnos = TurnosFalsos()
    respuesta = r("2", estado=_listo(), turnos=turnos)
    assert turnos.enviadas == [] and "no envié ninguna oferta" in respuesta.texto


def test_cancelar_desde_cualquier_paso():
    respuesta = r("cancelar", estado=en_paso(OFERTA_KG, sede="chimbas", variedad="Malbec"))
    assert respuesta.estado.paso == MENU and "no envié" in respuesta.texto


def test_regla_de_la_base_se_explica():
    turnos = TurnosFalsos(rechazo="este número no puede ofrecer uva para esa cuenta")
    respuesta = r("1", estado=_listo(), turnos=turnos)
    assert "No pude enviar la oferta: Este número no puede ofrecer uva para esa cuenta." in respuesta.texto


def test_motivo_en_palabras():
    assert motivo_en_palabras("el productor no está en la lista") == "El productor no está en la lista."
    assert motivo_en_palabras("entre 1000000 kg") == "Entre 1.000.000 kg."


def test_estado_del_borrador_ida_y_vuelta():
    borrador = Borrador("p-9", "chimbas", (("Cereza", 80_000),), "Malbec", ("Malbec",), True)
    assert Borrador.desde_dict(borrador.a_dict()) == borrador
    assert Borrador.desde_dict(None) is None
    # El borrador del pedido por día que haya quedado guardado se descarta.
    assert Borrador.desde_dict({"sede": "chimbas", "fecha": "2026-11-05", "camiones": 2}) is None
    assert Borrador().pedido != Borrador().pedido


# --- Mis turnos ----------------------------------------------------------------------------


def test_mis_turnos_muestra_ofertas_y_dias():
    turnos = TurnosFalsos(
        ofertas=[
            OfertaVigente(1, "chimbas", "20-1", "G03436", "Cereza", 80_000, "pendiente"),
            OfertaVigente(2, "chimbas", "20-1", "G03436", "Malbec", 40_000, "detenida", date(2026, 12, 1)),
        ],
        proximos=[TurnoVigente(7, "chimbas", HOY, "20-1", "G03436", 3, 1, 11_000, False)],
    )
    respuesta = r("4", turnos=turnos)
    assert respuesta.estado.paso == MENU
    assert "• Cereza, 80.000 kg en Chimbas: esperando que la bodega asigne los días" in respuesta.texto
    assert "• Malbec, 40.000 kg en Chimbas: postergada por falta de grado hasta el martes 01/12" in respuesta.texto
    assert "• Hoy 16/11 — Chimbas — 3 camiones de 11.000 kg (ya llegaron 1)" in respuesta.texto


def test_mis_turnos_vacio():
    assert "No tenés ofertas ni turnos" in r("mis turnos").texto


def test_mis_turnos_solo_de_cuentas_habilitadas():
    turnos = TurnosFalsos()
    r("mis turnos", cuentas=(JUAN, SOLO_INFORMES, FINCA), turnos=turnos)
    assert turnos.consultas == [("ofertas", ["20-1", "30-7"]), ("proximos", ["20-1", "30-7"], HOY)]


def test_paso_de_cuenta_sin_cuentas_habilitadas_no_rompe():
    cuenta = Cuenta("20-1", "G00001", "PRODUCTOR", frozenset({"ver_informes"}))
    respuesta = responder("1", [cuenta], Estado(OFERTA_CUENTA, "20-1"), date(2026, 10, 29),
                          puede_ver_informes=True, puede_pedir_turnos=False)
    assert respuesta.texto
