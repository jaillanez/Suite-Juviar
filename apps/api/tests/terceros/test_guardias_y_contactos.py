import pytest
from fastapi.testclient import TestClient

from suite_juviar.main import app
from suite_juviar.plataforma.terceros.api import contactos, guardias, tablero_fila

BODEGA = {"X-Perfil-Simulado": "BODEGA", "X-Actor-Simulado": "bodega"}


@pytest.fixture
def escrito(monkeypatch):
    llamadas = []
    monkeypatch.setattr(guardias, "_escribir", lambda sql, p: llamadas.append((sql, p)) or {})
    return llamadas


def test_rrhh_no_administra_tablets():
    assert TestClient(app).get("/api/v1/guardias", headers={"X-Perfil-Simulado": "RRHH"}).status_code == 403


def test_alta_de_tablet_manda_hash_y_devuelve_la_clave_una_vez(escrito):
    respuesta = TestClient(app).post("/api/v1/guardias", headers=BODEGA,
                                     json={"usuario": "porton.chimbas", "nombre": "Portón Chimbas", "sede": "chimbas"})
    assert respuesta.status_code == 201
    clave = respuesta.json()["clave_temporal"]
    sql, parametros = escrito[0]
    assert "fila.crear_guardia" in sql
    assert parametros["hash"].startswith("pbkdf2_sha256$600000$") and clave not in parametros["hash"]


def test_clave_nueva_y_baja_usan_las_funciones_de_la_base(escrito):
    cliente = TestClient(app)
    assert cliente.post("/api/v1/guardias/porton.chimbas/clave", headers=BODEGA).json()["clave_temporal"]
    assert cliente.post("/api/v1/guardias/porton.chimbas/baja", headers=BODEGA).status_code == 204
    assert cliente.put("/api/v1/guardias/porton.chimbas", headers=BODEGA,
                       json={"nombre": "Portón Lavalle", "sede": "lavalle"}).status_code == 204
    assert [s.split("(")[0] for s, _ in escrito] == [
        "SELECT fila.nueva_clave_guardia", "SELECT fila.baja_guardia", "SELECT fila.modificar_guardia"]


def test_no_deja_cargar_como_productor_un_celular_del_personal(monkeypatch):
    monkeypatch.setattr(tablero_fila, "_dsn", "postgresql://prueba")
    monkeypatch.setattr(tablero_fila, "_leer", lambda sql, p: [{"?column?": 1}] if p["t"] == "5492644567890" else [])
    with pytest.raises(Exception) as error:
        contactos._exigir_que_no_sea_personal("264 15 456-7890")
    assert error.value.status_code == 409
    contactos._exigir_que_no_sea_personal("2645550000")
