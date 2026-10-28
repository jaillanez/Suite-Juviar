"""Controles negativos de los defectos encontrados en la revisión del 22/09."""

from datetime import UTC, date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from fila_app import repositorio as R
from fila_app.main import app, repo_guardia, repo_turnos

TOKEN = "t" * 48


class Falso:
    def tablero(self, sede):
        return {"pendientes": [], "espera": [], "llamados": []}

    def reservar_turno(self, datos):
        return {"id": 1, **datos}


@pytest.fixture()
def cliente_sin_tokens(monkeypatch):
    for variable in ("FILA_GUARDIA_TOKEN", "FILA_PANTALLA_TOKEN", "FILA_TURNOS_TOKEN"):
        monkeypatch.delenv(variable, raising=False)
    app.dependency_overrides[repo_guardia] = lambda: Falso()
    app.dependency_overrides[repo_turnos] = lambda: Falso()
    yield TestClient(app)
    app.dependency_overrides.clear()


TURNO = {
    "sede": "chimbas",
    "fecha": "2026-09-22",
    "clientecuit": "20-11111111-1",
    "camiones": 1,
    "kg_por_camion": 11000,
    "pedido_por": "prueba",
}


def test_variable_sin_cargar_y_token_vacio_se_rechazan(cliente_sin_tokens):
    assert cliente_sin_tokens.get("/api/pantalla/chimbas?token=").status_code == 404
    assert (
        cliente_sin_tokens.post(
            "/api/turnos", json=TURNO, headers={"x-turnos-token": ""}
        ).status_code
        == 403
    )
    assert (
        cliente_sin_tokens.get(
            "/api/guardia/chimbas", headers={"x-guardia-token": ""}
        ).status_code
        == 403
    )


def test_token_corto_no_sirve(cliente_sin_tokens, monkeypatch):
    monkeypatch.setenv("FILA_PANTALLA_TOKEN", "corto")
    assert cliente_sin_tokens.get("/api/pantalla/chimbas?token=corto").status_code == 404


def test_control_negativo_token_correcto_entra(cliente_sin_tokens, monkeypatch):
    monkeypatch.setenv("FILA_PANTALLA_TOKEN", TOKEN)
    assert cliente_sin_tokens.get(f"/api/pantalla/chimbas?token={TOKEN}").status_code == 200
    assert cliente_sin_tokens.get(f"/api/pantalla/chimbas?token={TOKEN[:-1]}").status_code == 404


SJ = timezone(timedelta(hours=-3))


@pytest.mark.parametrize(
    "hora_local, esperado",
    [
        (datetime(2026, 3, 3, 22, 30, tzinfo=SJ), date(2026, 3, 3)),
        (datetime(2026, 3, 3, 0, 15, tzinfo=SJ), date(2026, 3, 3)),
        (datetime(2026, 3, 3, 21, 0, tzinfo=SJ), date(2026, 3, 3)),
    ],
)
def test_dia_operativo_es_el_de_san_juan(hora_local, esperado):
    assert R._dia_operativo(hora_local.astimezone(UTC)) == esperado


@pytest.mark.parametrize("accion", ["rechazar", "cancelar"])
@pytest.mark.parametrize("motivo", [None, "", "porque sí"])
def test_sacar_de_la_fila_exige_motivo_de_la_lista(accion, motivo):
    with pytest.raises(ValueError, match="motivo"):
        R.RepositorioFila("sin-conexion").accionar(
            1,
            accion,
            actor="guardia:tablet",
            id_cliente=uuid4(),
            momento_cliente=datetime.now(UTC),
            motivo=motivo,
        )
