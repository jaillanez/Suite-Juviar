from datetime import date
from decimal import Decimal

import pytest
from consulta_publica.bot.estadisticas import (
    Entrega,
    formatear_kg,
    resumir,
)
from consulta_publica.bot.periodos import cosecha_de, interpretar

HOY = date(2026, 3, 17)


@pytest.mark.parametrize("texto,desde,hasta", [
    ("Última cosecha", date(2025, 12, 1), date(2026, 11, 30)),
    ("cosecha 2025", date(2024, 12, 1), date(2025, 11, 30)),
    ("últimos 3 meses", date(2025, 12, 18), HOY),
    ("ultimos 6 meses", date(2025, 9, 19), HOY),
    ("marzo 2025", date(2025, 3, 1), date(2025, 3, 31)),
    ("febrero", date(2026, 2, 1), date(2026, 2, 28)),
    ("este año", date(2026, 1, 1), HOY),
    ("2024", date(2024, 1, 1), date(2024, 12, 31)),
    ("hoy", HOY, HOY),
])
def test_interpreta_lo_que_escribe_el_productor(texto, desde, hasta):
    p = interpretar(texto, HOY)
    assert (p.desde, p.hasta) == (desde, hasta)


@pytest.mark.parametrize("texto", [None, "", "cualquier cosa", "cosecha 1990", "últimos 0 meses", "2050"])
def test_lo_que_no_se_entiende_devuelve_nada(texto):
    assert interpretar(texto, HOY) is None


def test_diciembre_pertenece_a_la_cosecha_siguiente():
    assert cosecha_de(date(2025, 12, 15)) == 2026
    assert cosecha_de(date(2026, 3, 15)) == 2026


def _e(dia, variedad, neto, azucar=None):
    return Entrega(date(2026, 3, dia), f"c{dia}", variedad, neto, azucar)


def test_resumen_vacio():
    r = resumir([])
    assert r.total_kg == 0 and r.entregas == 0 and r.azucar_promedio is None


def test_totales_y_agrupacion():
    r = resumir([_e(9, "Pedro Gimenez", 9840), _e(9, "Pedro Gimenez", 8960), _e(19, "Cereza", 9200)])
    assert r.total_kg == 28000 and r.entregas == 3
    assert r.por_variedad == [("Pedro Gimenez", 18800), ("Cereza", 9200)]
    assert r.por_dia == [(date(2026, 3, 9), 18800), (date(2026, 3, 19), 9200)]


def test_azucar_se_pondera_por_kilos():
    r = resumir([_e(1, "Cereza", 1000, 200), _e(2, "Cereza", 9000, 230)])
    assert r.azucar_promedio == 227.0     # simple daría 215
    assert (r.azucar_min, r.azucar_max) == (200.0, 230.0)


def test_acepta_decimales_de_la_base():
    r = resumir([_e(1, "Cereza", 1000, Decimal("212.33"))])
    assert r.azucar_promedio == 212.3


def test_entregas_sin_peso_no_cuentan():
    r = resumir([_e(1, "Cereza", 0), _e(2, "Cereza", None), _e(3, "Cereza", 5000)])
    assert r.entregas == 1 and r.total_kg == 5000


def test_mas_de_tres_variedades_se_agrupan():
    r = resumir([_e(1, "A", 500), _e(2, "B", 400), _e(3, "C", 300), _e(4, "D", 200), _e(5, "E", 100)])
    assert r.por_variedad == [("A", 500), ("B", 400), ("C", 300), ("Otras", 300)]


def test_formato_de_kilos():
    assert formatear_kg(115920) == "115.920 kg" and formatear_kg(None) == "0 kg"
