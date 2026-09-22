from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from fila_app.main import app, repo_guardia, repo_publico, repo_turnos

GUARDIA_TOKEN = "g" * 32
PANTALLA_TOKEN = "p" * 32
TURNOS_TOKEN = "t" * 32


class Falso:
    def __init__(self):
        self.altas = []

    def autocompletar(self, patente, ip):
        return {"productor": "Patente reconocida"}

    def alta_publica(self, **datos):
        self.altas.append(datos)
        return {"ticket": "x" * 43, "estado": "pendiente", "patente": "AB123CD"}

    def ticket(self, token):
        return {"estado": "en_espera", "numero_dia": 7, "adelante": 2, "patente": "AB123CD"}

    def tablero(self, sede):
        return {"pendientes": [], "espera": [], "llamados": []}

    def confirmar(self, viaje_id, **datos):
        return {"id": viaje_id, "estado": "en_espera", **datos}

    def alta_directa(self, datos, actor):
        return {"id": 9, "estado": "en_espera", "actor": actor, **datos}

    def accionar(self, viaje_id, accion, **datos):
        return {"id": viaje_id, "accion": accion, **datos}

    def reservar_turno(self, datos):
        return {"id": 1, **datos}


def cliente(monkeypatch):
    monkeypatch.setenv("FILA_GUARDIA_TOKEN", GUARDIA_TOKEN)
    monkeypatch.setenv("FILA_PANTALLA_TOKEN", PANTALLA_TOKEN)
    monkeypatch.setenv("FILA_TURNOS_TOKEN", TURNOS_TOKEN)
    falso = Falso()
    app.dependency_overrides[repo_publico] = lambda: falso
    app.dependency_overrides[repo_guardia] = lambda: falso
    app.dependency_overrides[repo_turnos] = lambda: falso
    return TestClient(app), falso


def test_pagina_publica_no_expone_lista_de_productores(monkeypatch):
    c, _ = cliente(monkeypatch)
    texto = c.get("/r/chimbas").text
    assert "Productor" in texto
    assert "clientecuit" not in texto and "RODRIGUEZ" not in texto


def test_esquema_openapi_no_esta_publicado(monkeypatch):
    c, _ = cliente(monkeypatch)
    assert c.get("/openapi.json").status_code == 404


def test_autocompletar_no_expone_datos_del_chofer_y_recibe_ip(monkeypatch):
    c, _ = cliente(monkeypatch)
    respuesta = c.get("/api/publico/vehiculos/AB123CD")
    assert respuesta.json() == {"productor": "Patente reconocida"}
    assert "chofer" not in respuesta.text and "telefono" not in respuesta.text


def test_alta_publica_queda_pendiente(monkeypatch):
    c, falso = cliente(monkeypatch)
    r = c.post(
        "/api/publico/viajes",
        json={
            "sede": "chimbas",
            "patente": "ab 123 cd",
            "productor": "Nombre escrito",
            "telefono": None,
            "id_cliente": "fd8151f2-3e73-466f-b5e8-bca48ed26914",
        },
    )
    assert r.status_code == 201 and r.json()["estado"] == "pendiente"
    assert falso.altas[0]["ip"] == "testclient"


def test_ticket_muestra_solo_estado_operativo(monkeypatch):
    c, _ = cliente(monkeypatch)
    datos = c.get("/api/publico/tickets/" + "x" * 43).json()
    assert datos == {"estado": "en_espera", "numero_dia": 7, "adelante": 2, "patente": "AB123CD"}


def test_guardia_exige_credencial(monkeypatch):
    c, _ = cliente(monkeypatch)
    assert c.get("/api/guardia/chimbas").status_code == 403
    assert c.get("/api/guardia/chimbas", headers={"x-guardia-token": GUARDIA_TOKEN}).status_code == 200


def test_confirmacion_acepta_idempotencia_de_tablet(monkeypatch):
    c, _ = cliente(monkeypatch)
    r = c.post(
        "/api/guardia/viajes/4/confirmar",
        headers={"x-guardia-token": GUARDIA_TOKEN},
        json={
            "id_cliente": str(UUID("e72e072a-d725-4cf5-9127-0e8e972fd550")),
            "clientecuit": "20-12345678-9",
            "declara_organica": False,
            "momento_cliente": datetime.now(UTC).isoformat(),
        },
    )
    assert r.status_code == 200 and r.json()["estado"] == "en_espera"


def test_guardia_puede_dar_alta_sin_celular(monkeypatch):
    c, _ = cliente(monkeypatch)
    r = c.post(
        "/api/guardia/viajes/directo",
        headers={"x-guardia-token": GUARDIA_TOKEN},
        json={
            "id_cliente": "668e1368-b577-4cef-a112-a1934c4831af",
            "sede": "chimbas",
            "patente": "ABC123",
            "productor": "Productor informado",
            "clientecuit": "20-12345678-9",
            "declara_organica": False,
            "momento_cliente": datetime.now(UTC).isoformat(),
        },
    )
    assert r.status_code == 200 and r.json()["estado"] == "en_espera"


def test_pantalla_exige_token_y_no_tiene_productores(monkeypatch):
    c, _ = cliente(monkeypatch)
    assert c.get("/api/pantalla/chimbas").status_code == 404
    assert c.get("/api/pantalla/chimbas?token=mal").status_code == 404
    respuesta = c.get(f"/api/pantalla/chimbas?token={PANTALLA_TOKEN}")
    assert respuesta.json() == {"llamados": []}


def test_turno_exige_token(monkeypatch):
    c, _ = cliente(monkeypatch)
    datos = {
        "sede": "chimbas",
        "fecha": "2026-09-24",
        "clientecuit": "20-12345678-9",
        "camiones": 2,
        "kg_por_camion": 11000,
        "pedido_por": "5492645000001",
    }
    assert c.post("/api/turnos", json=datos).status_code == 403
    assert c.post("/api/turnos", json=datos, headers={"x-turnos-token": TURNOS_TOKEN}).status_code == 201


def test_tokens_ausentes_o_vacios_nunca_autorizan(monkeypatch):
    c, _ = cliente(monkeypatch)
    monkeypatch.delenv("FILA_GUARDIA_TOKEN")
    monkeypatch.delenv("FILA_PANTALLA_TOKEN")
    monkeypatch.delenv("FILA_TURNOS_TOKEN")
    assert c.get("/api/guardia/chimbas", headers={"x-guardia-token": ""}).status_code == 403
    assert c.get("/api/pantalla/chimbas?token=").status_code == 404


def test_accion_desconocida_no_llega_al_repositorio(monkeypatch):
    c, _ = cliente(monkeypatch)
    respuesta = c.post(
        "/api/guardia/viajes/4/borrar",
        headers={"x-guardia-token": GUARDIA_TOKEN},
        json={
            "id_cliente": "999de681-2cc1-45e9-8948-d9af0793f093",
            "momento_cliente": datetime.now(UTC).isoformat(),
        },
    )
    assert respuesta.status_code == 404
