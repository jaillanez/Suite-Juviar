from datetime import UTC, datetime

import pytest
from consulta_publica.api import descargas as api
from consulta_publica.api.descargas import Descarga, cargar_clave
from fastapi import FastAPI
from fastapi.testclient import TestClient

CLAVE = "k" * 40


class RepoFalso:
    def __init__(self) -> None:
        self.registros: list[tuple] = []
        self.pedidos: list[str] = []

    def ultima(self, nroinscripto):
        self.pedidos.append(nroinscripto)
        return Descarga(
            "chimbas",
            "12247369",
            "0000000476",
            datetime(2026, 3, 3, 12, 58, tzinfo=UTC),
            11560,
            "Cereza",
            222.0,
            "descargado",
        )

    def del_dia(self, nroinscripto, dia):
        return [
            Descarga(
                "chimbas",
                "1",
                "ID-1",
                datetime(2026, 3, 3, tzinfo=UTC),
                11560,
                "Cereza",
                222.0,
                "descargado",
            ),
            Descarga(
                "chimbas",
                "2",
                "ID-2",
                datetime(2026, 3, 3, tzinfo=UTC),
                11740,
                "Cereza",
                215.0,
                "descargado",
            ),
        ]

    def en_descarga(self, nroinscripto):
        return [
            Descarga("chimbas", "3", "ID-3", None, None, "Cereza", None, "en_descarga")
        ]

    def rango(self, nroinscripto, desde, hasta, limite):
        return []

    def datos_al(self):
        return {"chimbas": datetime(2026, 3, 3, 13, 0, tzinfo=UTC)}

    def registrar(self, *argumentos):
        self.registros.append(argumentos)


@pytest.fixture()
def cliente(monkeypatch):
    monkeypatch.setenv("CONSULTA_API_KEY_JUVIAR", CLAVE)
    api._clave.cache_clear()
    repo = RepoFalso()
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.obtener_repositorio] = lambda: repo
    cliente_prueba = TestClient(app)
    cliente_prueba.repo = repo
    yield cliente_prueba
    api._clave.cache_clear()


URL = "/v1/productores/J80123/ultima"


def test_sin_cabecera_rechaza(cliente) -> None:
    assert cliente.get(URL).status_code == 401


def test_cabecera_vacia_rechaza(cliente) -> None:
    assert cliente.get(URL, headers={"X-Api-Key": ""}).status_code == 401


def test_clave_incorrecta_rechaza(cliente) -> None:
    assert cliente.get(URL, headers={"X-Api-Key": "x" * 40}).status_code == 401


def test_clave_correcta_responde_y_registra(cliente) -> None:
    respuesta = cliente.get(URL, headers={"X-Api-Key": CLAVE})
    assert respuesta.status_code == 200
    assert respuesta.json()["descarga"]["neto_kg"] == 11560
    assert respuesta.json()["descarga"]["id_origen"] == "0000000476"
    assert cliente.repo.registros[0][1] == "J80123"


def test_rechazo_no_llega_al_repositorio(cliente) -> None:
    cliente.get(URL, headers={"X-Api-Key": "x" * 40})
    assert cliente.repo.pedidos == [] and cliente.repo.registros == []


def test_inscripto_con_caracteres_raros_se_rechaza(cliente) -> None:
    respuesta = cliente.get(
        "/v1/productores/J80%27%20OR%201=1/ultima", headers={"X-Api-Key": CLAVE}
    )
    assert respuesta.status_code == 422


def test_resumen_suma_kilos_y_cuenta_camiones_en_curso(cliente) -> None:
    respuesta = cliente.get(
        "/v1/productores/J80123/resumen?fecha=2026-03-03", headers={"X-Api-Key": CLAVE}
    )
    assert respuesta.json()["kilos_netos"] == 23300
    assert respuesta.json()["camiones_en_descarga"] == 1


@pytest.mark.parametrize("valor", ["", "corta"])
def test_sin_clave_configurada_no_arranca(monkeypatch, valor) -> None:
    monkeypatch.setenv("CONSULTA_API_KEY_JUVIAR", valor)
    with pytest.raises(RuntimeError):
        cargar_clave()


def test_clave_ausente_en_entorno_no_arranca(monkeypatch) -> None:
    monkeypatch.delenv("CONSULTA_API_KEY_JUVIAR", raising=False)
    with pytest.raises(RuntimeError):
        cargar_clave()
