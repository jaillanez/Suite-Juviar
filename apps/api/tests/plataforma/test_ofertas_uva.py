"""Ofertas de uva: reparto de días, historial, alertas y textos.

La última prueba corre contra una base DMZ real con infra/038 aplicada si se define
SJ_PRUEBA_DMZ_DSN (rol gestion_tablero); si no, se saltea.
"""

import os
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from suite_juviar.plataforma.terceros.api import ofertas_uva, tablero_fila
from suite_juviar.plataforma.terceros.api.ofertas_uva import (
    aviso_asignacion,
    aviso_detencion,
    con_capacidad,
    constancia,
    dias_habiles,
    repartir,
    resumir_historial,
    sobreoferta,
    temporada_de_oferta,
)

LUNES = date(2027, 2, 1)
BODEGA = {"X-Perfil-Simulado": "BODEGA"}


def test_dias_corridos_sin_domingos():
    dias = dias_habiles(date(2027, 2, 4), 4)  # jueves
    assert [d.isoformat() for d in dias] == ["2027-02-04", "2027-02-05", "2027-02-06", "2027-02-08"]


def test_ejemplos_de_la_reunion():
    # 80.000 kg a 10.000 por día son 8 días; 400.000 a 40.000 son 10.
    assert len(repartir(80_000, 10_000, LUNES, 10_000)) == 8
    reparto = repartir(400_000, 40_000, LUNES, 20_000)
    assert len(reparto) == 10 and all(d["camiones"] == 2 for d in reparto)
    assert reparto[-1]["fecha"] == date(2027, 2, 11)  # se saltea el domingo 7


def test_el_ultimo_dia_lleva_el_resto_y_si_no_llega_a_un_camion_se_suma_al_anterior():
    reparto = repartir(25_000, 10_000, LUNES, 10_000)
    assert [d["kg"] for d in reparto] == [10_000, 10_000, 5_000]
    reparto = repartir(20_500, 10_000, LUNES, 11_000)
    assert [d["kg"] for d in reparto] == [10_000, 10_500]
    assert reparto[-1]["camiones"] * reparto[-1]["kg_por_camion"] >= 10_500


def test_camiones_enteros_por_dia():
    d = repartir(30_000, 30_000, LUNES, 11_000)[0]
    assert d["camiones"] == 3 and d["kg_por_camion"] == 10_000


def test_rechaza_dias_imposibles():
    with pytest.raises(ValueError):
        repartir(10_000, 500, LUNES, 10_000)
    with pytest.raises(ValueError):
        repartir(3_000_000, 2_000_000, LUNES, 10_000)  # más de 50 camiones en un día


def test_pasarse_de_la_capacidad_avisa_pero_no_impide():
    reparto = repartir(30_000, 15_000, LUNES, 15_000)
    dias = con_capacidad(reparto, {LUNES: 20_000, LUNES + timedelta(days=1): None}, {LUNES: 10_000})
    assert dias[0]["libre_kg"] == 10_000 and dias[0]["exceso_kg"] == 5_000
    assert dias[1]["libre_kg"] is None and dias[1]["exceso_kg"] == 0


def _entrega(t, kg, variedad="Cereza"):
    return {"temporada": t, "variedad": variedad, "kg": kg,
            "desde": date(t, 2, 1), "hasta": date(t, 3, 1)}


def test_historial_de_los_ultimos_anios_y_sobreoferta():
    entregas = [_entrega(2024, 60_000), _entrega(2025, 80_000), _entrega(2025, 20_000, "Malbec"),
                _entrega(2026, 100_000), _entrega(2020, 999_999)]
    h = resumir_historial(entregas, 2027, 3)
    assert [a["temporada"] for a in h["anios"]] == [2024, 2025, 2026]
    assert [a["kg"] for a in h["anios"]] == [60_000, 100_000, 100_000]
    assert h["promedio_kg"] == 86_667 and constancia(h, 3) == "constante"
    assert h["anios"][1]["variedades"][0] == {"variedad": "Cereza", "kg": 80_000}
    assert sobreoferta(100_000, h["promedio_kg"], 0) == 13_333
    assert sobreoferta(100_000, h["promedio_kg"], 20) == 0
    assert sobreoferta(100_000, None, 0) == 0


def test_constancia_para_priorizar():
    assert constancia(resumir_historial([], 2027, 3), 3) == "nuevo"
    assert constancia(resumir_historial([_entrega(2026, 1)], 2027, 3), 3) == "solo_ultimo"
    assert constancia(resumir_historial([_entrega(2024, 1), _entrega(2026, 1)], 2027, 3), 3) == "algunos"


def test_temporada_de_la_oferta():
    assert temporada_de_oferta(date(2026, 11, 15)) == 2027
    assert temporada_de_oferta(date(2027, 2, 10)) == 2027
    assert temporada_de_oferta(date(2027, 6, 1)) == 2028


def test_textos_para_el_productor():
    texto = aviso_asignacion("PEREZ JUAN", "chimbas", "Cereza", repartir(25_000, 10_000, LUNES, 10_000))
    assert "Chimbas" in texto and "Cereza" in texto and "lunes 01/02" in texto and "miércoles 03/02" in texto
    assert "1 camión (5.000 kg)" in texto
    assert "domingo" not in aviso_detencion("PEREZ JUAN", "chimbas", "Cereza", date(2027, 2, 15))


def test_exige_permiso_y_conexion(monkeypatch):
    monkeypatch.setattr(tablero_fila, "_dsn", "")
    app = FastAPI()
    app.include_router(ofertas_uva.router)
    cliente = TestClient(app)
    assert cliente.get("/turnos-bodega/ofertas", params={"sede": "chimbas"},
                       headers={"X-Perfil-Simulado": "MEDICO"}).status_code == 403
    assert cliente.get("/turnos-bodega/ofertas", params={"sede": "chimbas"}, headers=BODEGA).status_code == 503
    assert cliente.post("/turnos-bodega/ofertas", headers=BODEGA, json={
        "sede": "chimbas", "cuit": "123", "variedad": "Cereza", "kg": 10_000}).status_code == 422


@pytest.mark.skipif(not os.getenv("SJ_PRUEBA_DMZ_DSN"), reason="sin base DMZ de prueba")
def test_recorrido_completo_contra_la_base(monkeypatch):
    monkeypatch.setattr(tablero_fila, "_dsn", os.environ["SJ_PRUEBA_DMZ_DSN"])
    app = FastAPI()
    app.include_router(ofertas_uva.router)
    c = TestClient(app)
    nueva = c.post("/turnos-bodega/ofertas", headers=BODEGA, json={
        "sede": "chimbas", "cuit": "20111111112", "variedad": "Cereza", "kg": 25_000})
    assert nueva.status_code == 201, nueva.text
    oferta_id = nueva.json()["id"]
    sin_nombre = c.post("/turnos-bodega/ofertas", headers=BODEGA, json={
        "sede": "chimbas", "cuit": "20333333334", "variedad": "Malbec", "kg": 9_000})
    assert sin_nombre.status_code == 409
    nn = c.post("/turnos-bodega/ofertas", headers=BODEGA, json={
        "sede": "chimbas", "cuit": "20333333334", "nombre_nuevo": "Finca Nueva", "variedad": "Malbec", "kg": 9_000})
    assert nn.status_code == 201, nn.text

    lista = c.get("/turnos-bodega/ofertas", params={"sede": "chimbas"}, headers=BODEGA).json()
    o = next(x for x in lista["ofertas"] if x["id"] == oferta_id)
    assert o["estado"] == "pendiente" and o["historial"]["anios_con_entregas"] >= 1
    assert next(x for x in lista["ofertas"] if x["cuit"] == "20333333334")["productor_nuevo"]

    inicio = date.today() + timedelta(days=3)
    previa = c.post(f"/turnos-bodega/ofertas/{oferta_id}/vista-previa", headers=BODEGA,
                    json={"inicio": inicio.isoformat(), "kg_dia": 10_000})
    assert previa.status_code == 200, previa.text
    assert len(previa.json()["dias"]) == 3 and "Cereza" in previa.json()["aviso"]
    asignada = c.post(f"/turnos-bodega/ofertas/{oferta_id}/asignar", headers=BODEGA,
                      json={"inicio": inicio.isoformat(), "kg_dia": 10_000})
    assert asignada.status_code == 200, asignada.text
    otra_vez = c.post(f"/turnos-bodega/ofertas/{oferta_id}/asignar", headers=BODEGA,
                      json={"inicio": inicio.isoformat(), "kg_dia": 10_000})
    assert otra_vez.status_code == 409

    detenida = c.post(f"/turnos-bodega/ofertas/{oferta_id}/detener", headers=BODEGA, json={"semanas": 1})
    assert detenida.status_code == 200, detenida.text
    lista = c.get("/turnos-bodega/ofertas", params={"sede": "chimbas"}, headers=BODEGA).json()
    o = next(x for x in lista["ofertas"] if x["id"] == oferta_id)
    assert o["estado"] == "detenida" and o["kg_a_programar"] == 25_000 and o["dias"] == 0
    assert c.post(f"/turnos-bodega/ofertas/{oferta_id}/detener", headers=BODEGA,
                  json={"semanas": 5}).status_code == 422
