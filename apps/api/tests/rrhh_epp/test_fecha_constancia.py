"""La fecha que se imprime en la constancia es la de San Juan, no la del reloj del servidor.

La constancia es un papel que el trabajador firma con una fecha escrita. Con el
servidor en UTC, toda entrega posterior a las 21:00 de San Juan quedaba fechada
al día siguiente, y el papel firmado no coincidía con el día en que se entregó.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from suite_juviar.modulos.rrhh_epp.application.servicios_mvp import ZONA_OPERATIVA

SAN_JUAN = ZoneInfo("America/Argentina/San_Juan")


def entregar(contenedor, **cambios):
    argumentos = {
        "numero_legajo": "1042",
        "items": [{"codigo": "68", "item_codigo": "SIM-68-01", "cantidad": 1}],
        "metodo_firma": "TRAZO_TABLET",
        "evidencia_firma": "data:image/png;base64,AAAA",
        "usuario_deposito": "deposito",
    }
    argumentos.update(cambios)
    return contenedor.registrar_entrega.ejecutar(**argumentos)


def test_entrega_de_la_noche_lleva_la_fecha_de_san_juan(contenedor):
    # El instante llega expresado en UTC, que es como lo produce el servidor:
    # 01:30 del 23/09 en UTC son las 22:30 del 22/09 en San Juan.
    momento = datetime(2026, 9, 22, 22, 30, tzinfo=SAN_JUAN).astimezone(UTC)
    assert momento.date().isoformat() == "2026-09-23", "el caso tiene que cruzar el día en UTC"

    entrega = entregar(contenedor, entregada_en=momento)

    assert entrega.fecha_entrega.isoformat() == "2026-09-22"


def test_entrega_sin_hora_declarada_usa_el_reloj_de_san_juan(contenedor):
    # Camino real: la tablet no manda hora y el servidor toma datetime.now(UTC).
    esperada = datetime.now(UTC).astimezone(SAN_JUAN).date()
    assert entregar(contenedor).fecha_entrega == esperada


def test_entrega_de_la_manana_no_se_corre(contenedor):
    momento = datetime(2026, 9, 22, 9, 0, tzinfo=SAN_JUAN).astimezone(UTC)
    assert entregar(contenedor, entregada_en=momento).fecha_entrega.isoformat() == "2026-09-22"


def test_la_zona_operativa_es_san_juan():
    # Control negativo del propio arreglo: si alguien vuelve a poner UTC, esto falla.
    assert ZONA_OPERATIVA.key == "America/Argentina/San_Juan"
    assert ZONA_OPERATIVA != UTC
