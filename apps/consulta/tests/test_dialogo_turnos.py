from datetime import date, timedelta

import pytest
from consulta_publica.bot.dialogo import (
    MENU,
    SIN_PERMISO_INFORMES,
    TURNO_CAMIONES,
    TURNO_CONFIRMAR,
    TURNO_CUENTA,
    TURNO_DIA,
    TURNO_KG,
    TURNO_ORGANICA,
    TURNO_SEDE,
    Cuenta,
    Estado,
    responder,
)
from consulta_publica.bot.turnos import (
    Borrador,
    TurnoRechazado,
    TurnoVigente,
    fecha_escrita,
    kilos_escritos,
    motivo_en_palabras,
)

ESTADISTICAS_FECHA = date(2026, 3, 17)        # BOT_FECHA_SIMULADA
HOY = date(2026, 10, 29)                      # fecha real (jueves)
TODO = frozenset({"ver_informes", "pedir_turnos", "administrar_contactos"})
JUAN = Cuenta("20-1", "G03436", "QUIROGA JUAN CARLOS.", TODO)
FINCA = Cuenta("30-7", "F001", "FINCA LOS ALAMOS SA", frozenset({"pedir_turnos"}))
SOLO_INFORMES = Cuenta("20-9", "H09870", "BARASSI ANGELA MARIA", frozenset({"ver_informes"}))


class TurnosFalsos:
    def __init__(self, capacidad=None, reservado=None, organico=False, kg=10_200,
                 rechazo=None, proximos=()):
        # Por defecto: 150 t todos los días, salvo el 31/10 que no tiene cupo definido.
        self.capacidad = capacidad if capacidad is not None else {
            HOY + timedelta(days=i): 150_000 for i in range(70) if i != 2
        }
        self.reservado = reservado or {}
        self.organico = organico
        self.kg = kg
        self.rechazo = rechazo
        self.lista = list(proximos)
        self.reservas = []
        self.consultas_proximos = []

    def libres(self, sede, desde, hasta):
        assert sede in {"chimbas", "lavalle", "media-agua"}
        dias = {}
        dia = desde
        while dia <= hasta:
            if dia in self.capacidad:
                dias[dia] = max(self.capacidad[dia] - self.reservado.get(dia, 0), 0)
            dia += timedelta(days=1)
        return dias

    def tiene_organico(self, clientecuit, fecha):
        return self.organico

    def kg_estimado(self, clientecuit):
        return self.kg

    def proximos(self, clientecuits, desde):
        self.consultas_proximos.append((clientecuits, desde))
        return self.lista

    def reservar(self, clientecuit, codigo, sede, fecha, camiones, kg_por_camion, organica):
        self.reservas.append(
            (clientecuit, codigo, sede, fecha, camiones, kg_por_camion, organica)
        )
        if self.rechazo:
            raise TurnoRechazado(self.rechazo)
        return TurnoVigente(41, sede, fecha, clientecuit, codigo, camiones, 0,
                            kg_por_camion, organica)


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


def test_menu_muestra_pedir_turno_y_mis_turnos():
    respuesta = r("hola")
    assert respuesta.opciones == [
        "Ver estadísticas", "Descargar reporte", "Pedir turno", "Mis turnos", "Mis contactos",
    ]


def test_sin_tarea_pedir_turnos_no_hay_opcion_de_turno():
    respuesta = r("hola", cuentas=(SOLO_INFORMES,))
    assert "Pedir turno" not in respuesta.opciones
    assert r("turno", cuentas=(SOLO_INFORMES,)).estado.paso == MENU


def test_sin_repositorio_de_turnos_el_menu_queda_como_antes():
    respuesta = responder("hola", [JUAN], Estado(), ESTADISTICAS_FECHA, puede_pedir_turnos=True)
    assert "Pedir turno" not in respuesta.opciones


def test_numero_que_solo_pide_turnos_ve_menu_de_turnos():
    respuesta = r("hola", cuentas=(FINCA,), informes=False)
    assert respuesta.opciones == ["Pedir turno", "Mis turnos", "Mis contactos"]
    pide_informe = r("ver estadisticas", cuentas=(FINCA,), informes=False)
    assert pide_informe.estado.paso == MENU and SIN_PERMISO_INFORMES in pide_informe.texto


def test_sin_ningun_permiso_sigue_el_aviso():
    assert r("hola", cuentas=(SOLO_INFORMES,), informes=False).texto == SIN_PERMISO_INFORMES


# --- Cuenta y bodega ----------------------------------------------------------------


def test_pedir_turno_con_la_cuenta_del_menu_va_directo_a_la_bodega():
    respuesta = r("3")
    assert respuesta.estado.paso == TURNO_SEDE and respuesta.estado.cuenta == "20-1"
    assert respuesta.opciones == ["Chimbas", "Lavalle", "Media Agua"]
    assert "QUIROGA JUAN CARLOS (G03436)" in respuesta.texto


def test_varias_cuentas_que_no_pueden_pedir_desde_el_menu_pregunta_cual():
    otra = Cuenta("30-8", "F002", "VIÑAS DEL SUR", frozenset({"pedir_turnos"}))
    cuentas = (SOLO_INFORMES, FINCA, otra)
    respuesta = r("pedir turno", cuentas=cuentas)
    assert respuesta.estado.paso == TURNO_CUENTA
    assert respuesta.opciones == ["FINCA LOS ALAMOS SA (F001)", "VIÑAS DEL SUR (F002)"]
    elegida = r("2", estado=respuesta.estado, cuentas=cuentas)
    assert elegida.estado.paso == TURNO_SEDE and elegida.estado.cuenta == "30-8"


def test_cuenta_turno_que_no_se_entiende_vuelve_a_preguntar():
    cuentas = (SOLO_INFORMES, FINCA, Cuenta("30-8", "F002", "X", frozenset({"pedir_turnos"})))
    respuesta = r("9", estado=Estado(TURNO_CUENTA, "30-7"), cuentas=cuentas)
    assert respuesta.estado.paso == TURNO_CUENTA


def test_una_sola_cuenta_habilitada_se_usa_sin_preguntar():
    respuesta = r("pedir turno", cuentas=(SOLO_INFORMES, FINCA))
    assert respuesta.estado.paso == TURNO_SEDE and respuesta.estado.cuenta == "30-7"


@pytest.mark.parametrize(("texto", "sede"), [("2", "lavalle"), ("media agua", "media-agua")])
def test_elegir_bodega_por_numero_o_nombre(texto, sede):
    respuesta = r(texto, estado=en_paso(TURNO_SEDE))
    assert respuesta.estado.paso == TURNO_DIA and respuesta.estado.turno.sede == sede


def test_bodega_que_no_existe():
    respuesta = r("san martin", estado=en_paso(TURNO_SEDE))
    assert respuesta.estado.paso == TURNO_SEDE and "No entendí la bodega" in respuesta.texto


# --- Día ------------------------------------------------------------------------------


def test_lista_de_dias_sale_de_capacidad_menos_reservado():
    turnos = TurnosFalsos(reservado={HOY: 150_000, HOY + timedelta(days=1): 139_500})
    respuesta = r("1", estado=en_paso(TURNO_SEDE), turnos=turnos)
    # Hoy lleno, el 31/10 sin cupo definido: no se ofrecen.
    assert respuesta.opciones[:3] == [
        "Mañana 30/10 — 10,5 t libres",
        "Dom 01/11 — 150 t libres",
        "Lun 02/11 — 150 t libres",
    ]
    assert len(respuesta.opciones) == 8 and respuesta.opciones[-1] == "Otra bodega"
    assert respuesta.estado.turno.dias[0] == HOY + timedelta(days=1)


def test_sin_dias_con_lugar_lo_dice_y_deja_cambiar_de_bodega():
    respuesta = r("1", estado=en_paso(TURNO_SEDE), turnos=TurnosFalsos(capacidad={}))
    assert "no quedan días con lugar" in respuesta.texto
    assert respuesta.opciones == ["Otra bodega"]
    assert r("1", estado=respuesta.estado).estado.paso == TURNO_SEDE


def test_elegir_dia_por_numero_usa_la_lista_que_se_mostro():
    dias = (date(2026, 11, 5), date(2026, 11, 6))
    respuesta = r("2", estado=en_paso(TURNO_DIA, sede="chimbas", dias=dias))
    assert respuesta.estado.paso == TURNO_CAMIONES
    assert respuesta.estado.turno.fecha == date(2026, 11, 6)
    assert "quedan 150 t libres" in respuesta.texto and "viernes 06/11" in respuesta.texto


def test_fecha_escrita():
    respuesta = r("05/11", estado=en_paso(TURNO_DIA, sede="lavalle"))
    assert respuesta.estado.paso == TURNO_CAMIONES
    assert respuesta.estado.turno.fecha == date(2026, 11, 5)


@pytest.mark.parametrize(
    ("texto", "aviso"),
    [
        ("31/10", "todavía no definió el cupo"),
        ("28/10/2026", "ya pasó"),
        ("15/02/2027", "60 días"),
        ("cualquier día", "No entendí el día"),
    ],
)
def test_fecha_que_no_sirve_vuelve_a_la_lista(texto, aviso):
    respuesta = r(texto, estado=en_paso(TURNO_DIA, sede="chimbas"))
    assert respuesta.estado.paso == TURNO_DIA and aviso in respuesta.texto


def test_dia_lleno_escrito_a_mano():
    turnos = TurnosFalsos(reservado={date(2026, 11, 5): 149_500})
    respuesta = r("5/11", estado=en_paso(TURNO_DIA, sede="chimbas"), turnos=turnos)
    assert respuesta.estado.paso == TURNO_DIA and "ya no queda lugar" in respuesta.texto


def test_interpretar_fechas():
    assert fecha_escrita("mañana", HOY) == date(2026, 10, 30)
    assert fecha_escrita("jueves 5/11", HOY) == date(2026, 11, 5)
    assert fecha_escrita("02-01", HOY) == date(2027, 1, 2)          # sin año: la próxima
    assert fecha_escrita("31/02", HOY) is None


# --- Camiones, kilos y orgánica --------------------------------------------------------


def _con_dia(**extra):
    return en_paso(TURNO_CAMIONES, sede="chimbas", fecha=date(2026, 11, 5), **extra)


@pytest.mark.parametrize("texto", ["0x", "51", "muchos", "-3"])
def test_camiones_fuera_de_rango(texto):
    respuesta = r(texto, estado=_con_dia())
    if texto == "-3":   # se lee el 3: se acepta
        assert respuesta.estado.paso == TURNO_KG
    else:
        assert respuesta.estado.paso == TURNO_CAMIONES and "entre 1 y 50" in respuesta.texto


def test_camiones_ofrece_el_estimado_de_kilos():
    respuesta = r("3 camiones", estado=_con_dia(), turnos=TurnosFalsos(kg=10_200))
    assert respuesta.estado.paso == TURNO_KG and respuesta.estado.turno.camiones == 3
    assert respuesta.opciones == ["Sí, 10.200 kg por camión"]


def test_kilos_confirmando_el_estimado_sin_organico_va_al_resumen():
    estado = en_paso(TURNO_KG, sede="chimbas", fecha=date(2026, 11, 5), camiones=3,
                     kg_sugerido=10_200)
    respuesta = r("1", estado=estado)
    assert respuesta.estado.paso == TURNO_CONFIRMAR
    assert respuesta.estado.turno.kg_por_camion == 10_200
    assert respuesta.estado.turno.organica is False


@pytest.mark.parametrize("texto", ["500", "41000", "mucho"])
def test_kilos_invalidos(texto):
    estado = en_paso(TURNO_KG, sede="chimbas", fecha=date(2026, 11, 5), camiones=3,
                     kg_sugerido=10_200)
    respuesta = r(texto, estado=estado)
    assert respuesta.estado.paso == TURNO_KG and "No me cerró" in respuesta.texto


def test_interpretar_kilos():
    assert kilos_escritos("12.500") == 12_500
    assert kilos_escritos("12 500 kg") == 12_500
    assert kilos_escritos("12,5 t") == 12_500
    assert kilos_escritos("doce") is None


def test_con_certificado_pregunta_si_es_organica():
    estado = en_paso(TURNO_KG, sede="chimbas", fecha=date(2026, 11, 5), camiones=2,
                     kg_sugerido=11_000)
    respuesta = r("12000", estado=estado, turnos=TurnosFalsos(organico=True))
    assert respuesta.estado.paso == TURNO_ORGANICA
    resumen = r("1", estado=respuesta.estado, turnos=TurnosFalsos(organico=True))
    assert resumen.estado.paso == TURNO_CONFIRMAR and resumen.estado.turno.organica is True
    assert "Uva orgánica: sí" in resumen.texto


# --- Confirmación ------------------------------------------------------------------------


def _listo_para_confirmar(**extra):
    datos = {"sede": "media-agua", "fecha": date(2026, 11, 5), "camiones": 2,
             "kg_por_camion": 11_000, "kg_sugerido": 11_000, "organica": False}
    datos.update(extra)
    return en_paso(TURNO_CONFIRMAR, **datos)


def test_resumen_muestra_el_pedido():
    respuesta = r("ok?", estado=_listo_para_confirmar())
    assert respuesta.estado.paso == TURNO_CONFIRMAR
    assert "Bodega: Media Agua" in respuesta.texto
    assert "Día: jueves 05/11" in respuesta.texto
    assert "2 camiones de 11.000 kg (22.000 kg en total)" in respuesta.texto


def test_confirmar_reserva_con_los_datos_del_pedido():
    turnos = TurnosFalsos()
    respuesta = r("1", estado=_listo_para_confirmar(organica=True), turnos=turnos)
    assert turnos.reservas == [
        ("20-1", "G03436", "media-agua", date(2026, 11, 5), 2, 11_000, True)
    ]
    assert respuesta.estado == Estado(MENU, "20-1")
    assert "Turno N° 41 pedido" in respuesta.texto
    assert "Media Agua, jueves 05/11: 2 camiones de 11.000 kg, uva orgánica" in respuesta.texto
    assert "Pedir turno" in respuesta.opciones


def test_cancelar_no_reserva():
    turnos = TurnosFalsos()
    respuesta = r("2", estado=_listo_para_confirmar(), turnos=turnos)
    assert turnos.reservas == [] and respuesta.estado.paso == MENU
    assert "no pedí ningún turno" in respuesta.texto


def test_cancelar_desde_cualquier_paso():
    turnos = TurnosFalsos()
    respuesta = r("cancelar", estado=_con_dia(), turnos=turnos)
    assert respuesta.estado == Estado(MENU, "20-1") and turnos.reservas == []


def test_regla_de_la_base_se_explica_y_ofrece_otro_dia():
    turnos = TurnosFalsos(rechazo="sin cupo: quedan 5000 kg para ese día",
                          reservado={date(2026, 11, 5): 145_000})
    respuesta = r("si", estado=_listo_para_confirmar(), turnos=turnos)
    assert len(turnos.reservas) == 1
    assert respuesta.estado.paso == TURNO_DIA
    assert "No pude pedir el turno: No alcanza el lugar de ese día: quedan 5.000 kg" in (
        respuesta.texto
    )
    # El 05/11 ya no se ofrece para 22 t; se conservan camiones y kilos.
    assert date(2026, 11, 5) not in respuesta.estado.turno.dias
    assert respuesta.estado.turno.camiones == 2
    otro = r("1", estado=respuesta.estado, turnos=turnos)
    assert otro.estado.paso == TURNO_CONFIRMAR and otro.estado.turno.fecha == date(2026, 10, 29)


def test_motivo_en_palabras():
    assert motivo_en_palabras("el productor no está en la lista") == (
        "El productor no está en la lista."
    )


def test_estado_del_borrador_ida_y_vuelta():
    borrador = Borrador("chimbas", date(2026, 11, 5), 2, 11_000, 10_200, True,
                        (date(2026, 11, 5),))
    assert Borrador.desde_dict(borrador.a_dict()) == borrador
    assert Borrador.desde_dict(None) is None


# --- Mis turnos ----------------------------------------------------------------------------


def test_mis_turnos_lista_los_proximos():
    turnos = TurnosFalsos(proximos=[
        TurnoVigente(7, "chimbas", HOY, "20-1", "G03436", 3, 1, 11_000, False),
        TurnoVigente(9, "lavalle", date(2026, 11, 3), "20-1", "G03436", 1, 0, 9_500, True),
    ])
    respuesta = r("4", turnos=turnos)
    assert turnos.consultas_proximos == [(["20-1"], HOY)]
    assert respuesta.estado.paso == MENU
    assert "• Hoy 29/10 — Chimbas — 3 camiones de 11.000 kg (ya llegaron 1)" in respuesta.texto
    assert "• Mar 03/11 — Lavalle — 1 camión de 9.500 kg, orgánica" in respuesta.texto


def test_mis_turnos_vacio():
    assert "No tenés turnos pedidos" in r("mis turnos").texto


def test_mis_turnos_solo_de_cuentas_habilitadas():
    turnos = TurnosFalsos()
    r("mis turnos", cuentas=(JUAN, SOLO_INFORMES, FINCA), turnos=turnos)
    assert turnos.consultas_proximos == [(["20-1", "30-7"], HOY)]
