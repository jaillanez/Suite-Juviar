"""Sesión orgánica en Gestión: permisos, validación de franjas y recorrido contra la base.

La última prueba corre contra una base DMZ real con infra/039 aplicada si se define
SJ_PRUEBA_DMZ_DSN (rol gestion_tablero); si no, se saltea.
"""

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from suite_juviar.plataforma.terceros.api import sesion_organica, tablero_fila
from suite_juviar.plataforma.terceros.api.sesion_organica import Parametros

BODEGA = {"X-Perfil-Simulado": "BODEGA"}
BASCULA = {"X-Perfil-Simulado": "BASCULA"}
MEDICO = {"X-Perfil-Simulado": "MEDICO"}
PARAMETROS = {"recibe_organica": True, "quien_abre": "ambos", "modo_franjas": "fijas",
              "inicio_cosecha": "2027-01-10", "dias_prioridad": 15,
              "franjas": [{"dia": 1, "desde": "08:00", "hasta": "13:00"},
                          {"dia": 1, "desde": "15:00", "hasta": "18:00"}]}


def _cliente():
    app = FastAPI()
    app.include_router(sesion_organica.router)
    app.include_router(tablero_fila.router)
    return TestClient(app)


def test_franjas_validas_y_sin_superponer():
    assert len(Parametros(**PARAMETROS).franjas) == 2
    with pytest.raises(ValidationError, match="empezar antes de terminar"):
        Parametros(**{**PARAMETROS, "franjas": [{"dia": 2, "desde": "12:00", "hasta": "08:00"}]})
    with pytest.raises(ValidationError, match="se superponen el martes"):
        Parametros(**{**PARAMETROS, "franjas": [{"dia": 2, "desde": "08:00", "hasta": "12:00"},
                                                {"dia": 2, "desde": "11:00", "hasta": "14:00"}]})
    with pytest.raises(ValidationError):
        Parametros(**{**PARAMETROS, "quien_abre": "chofer"})


def test_bodega_configura_y_bascula_abre(monkeypatch):
    monkeypatch.setattr(tablero_fila, "_dsn", "")
    c = _cliente()
    assert c.get("/fila-organica", headers=MEDICO).status_code == 403
    assert c.get("/fila-organica", headers=BASCULA).status_code == 503
    assert c.put("/fila-organica/chimbas", headers=BASCULA, json=PARAMETROS).status_code == 403
    assert c.put("/fila-organica/chimbas", headers=BODEGA, json=PARAMETROS).status_code == 503
    assert c.post("/fila-organica/chimbas/abrir", headers=BODEGA).status_code == 403
    assert c.post("/fila-organica/chimbas/abrir", headers=BASCULA).status_code == 503
    assert c.post("/fila-organica/chimbas/borrar", headers=BASCULA).status_code == 404
    assert c.post("/fila-organica/otra/abrir", headers=BASCULA).status_code == 404
    assert c.get("/fila-tablero/fotos/1", headers=MEDICO).status_code == 403
    assert c.get("/fila-tablero/fotos/1", headers=BASCULA).status_code == 503


@pytest.mark.skipif(not os.getenv("SJ_PRUEBA_DMZ_DSN"), reason="sin base DMZ de prueba")
def test_recorrido_completo_contra_la_base(monkeypatch):
    monkeypatch.setattr(tablero_fila, "_dsn", os.environ["SJ_PRUEBA_DMZ_DSN"])
    c = _cliente()
    manual = {**PARAMETROS, "modo_franjas": "manual", "quien_abre": "bascula", "franjas": []}
    assert c.put("/fila-organica/chimbas", headers=BODEGA, json=manual).status_code == 200
    abierta = c.post("/fila-organica/chimbas/abrir", headers=BASCULA)
    assert abierta.status_code == 200, abierta.text
    assert abierta.json()["abierta"] and abierta.json()["abierta_desde"] == "bascula"
    otra = c.post("/fila-organica/chimbas/abrir", headers=BASCULA)
    assert otra.status_code == 409 and "ya está abierta" in otra.json()["detail"]
    tablero = c.get("/fila-tablero", headers=BASCULA).json()
    chimbas = next(s for s in tablero["sedes"] if s["sede"] == "chimbas")
    assert chimbas["organica"]["abierta"]
    assert c.post("/fila-organica/chimbas/cerrar", headers=BASCULA).json()["abierta"] is False

    # Con franjas fijas no se abre a mano y la sesión manual que quedara se cierra.
    assert c.put("/fila-organica/chimbas", headers=BODEGA, json=PARAMETROS).status_code == 200
    fija = c.post("/fila-organica/chimbas/abrir", headers=BASCULA)
    assert fija.status_code == 409 and "franjas" in fija.json()["detail"]
    conf = next(s for s in c.get("/fila-organica", headers=BODEGA).json()["sedes"] if s["sede"] == "chimbas")
    assert conf["parametros"]["modo_franjas"] == "fijas" and len(conf["franjas"]) == 2
    assert conf["sesiones"][0]["cerrada_desde"] == "bascula"
