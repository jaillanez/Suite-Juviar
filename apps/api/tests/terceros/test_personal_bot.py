from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from suite_juviar.main import app
from suite_juviar.plataforma.terceros.api import personal_bot

ADMIN = {"X-Perfil-Simulado": "SUPERADMIN", "X-Actor-Simulado": "admin"}
PERSONA = SimpleNamespace(legajo="1210", nombre_completo="Quiroga, Carlos Alberto", empresa="ENAV",
                          sector="BODEGA", puesto="CAPATAZ")


@pytest.fixture
def escrito(monkeypatch):
    llamadas = []
    monkeypatch.setattr(personal_bot, "_escribir", lambda sql, p: llamadas.append((sql, p)) or p)
    personal_bot.configurar(lambda **_: [PERSONA], lambda legajo: PERSONA if legajo == "1210" else None)
    return llamadas


def test_bodega_no_puede_cargar_personal():
    respuesta = TestClient(app).get("/api/v1/personal-bot", headers={"X-Perfil-Simulado": "BODEGA"})
    assert respuesta.status_code == 403


def test_nombre_y_empresa_salen_del_legajo_y_el_celular_se_normaliza(escrito):
    respuesta = TestClient(app).post("/api/v1/personal-bot", headers=ADMIN,
                                     json={"telefono": "264 15 456-7890", "legajo": "1210", "tipo": "mando_medio"})
    assert respuesta.status_code == 201
    _, parametros = escrito[0]
    assert parametros == {"telefono": "5492644567890", "legajo": "1210", "nombre": "Quiroga, Carlos Alberto",
                          "empresa": "ENAV", "tipo": "mando_medio", "actor": parametros["actor"]}


def test_legajo_inexistente_y_tipo_invalido_se_rechazan(escrito):
    cliente = TestClient(app)
    assert cliente.post("/api/v1/personal-bot", headers=ADMIN,
                        json={"telefono": "2644567890", "legajo": "9999", "tipo": "personal"}).status_code == 404
    assert cliente.post("/api/v1/personal-bot", headers=ADMIN,
                        json={"telefono": "2644567890", "legajo": "1210", "tipo": "gerente"}).status_code == 422
    assert not escrito


def test_busca_personas_por_legajo_o_apellido(escrito):
    respuesta = TestClient(app).get("/api/v1/personal-bot/personas?q=quiroga", headers=ADMIN)
    assert respuesta.json()[0]["nombre"] == "Quiroga, Carlos Alberto"
