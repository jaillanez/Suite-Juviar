from datetime import UTC, date, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from suite_juviar.plataforma.terceros.api import tablero_fila
from suite_juviar.plataforma.terceros.api.tablero_fila import armar_tablero

HOY = date(2026, 10, 29)


def viaje(sede, estado, *, registrado=datetime(2026, 10, 29, 13, 0, tzinfo=UTC), **extra):
    return {
        "sede": sede, "numero_dia": extra.get("numero", 1), "patente": extra.get("patente", "AA123BB"),
        "productor_texto": "Finca Los Álamos", "estado": estado, "declara_organica": False,
        "variedad_declarada": extra.get("declarada"), "registrado_en": registrado,
        "confirmado_en": None, "llamado_en": None, "en_bascula_en": None, "cerrado_en": None,
        "variedad_bascula": extra.get("bascula"), "neto": extra.get("neto"), "azucar": None,
    }


def test_agrupa_por_bodega_y_cuenta_los_del_dia():
    ayer = datetime(2026, 10, 28, 13, 0, tzinfo=UTC)
    filas = [
        viaje("chimbas", "en_espera", declarada="Malbec"),
        viaje("chimbas", "descargado", declarada="Malbec", bascula="Malbec", neto=12000),
        viaje("chimbas", "cancelado"),
        viaje("lavalle", "llamado", registrado=ayer),
    ]
    datos = armar_tablero(filas, HOY, ["chimbas", "lavalle", "media-agua"])
    por_sede = {s["sede"]: s for s in datos["sedes"]}
    assert [s["nombre"] for s in datos["sedes"]] == ["Chimbas", "Lavalle", "Media Agua"]
    assert por_sede["chimbas"]["anotados_hoy"] == 2
    assert por_sede["chimbas"]["en_espera"] == 1
    assert por_sede["chimbas"]["descargados_hoy"] == 1
    assert len(por_sede["chimbas"]["camiones"]) == 2
    assert por_sede["chimbas"]["camiones"][1]["variedad_bascula"] == "Malbec"
    assert por_sede["lavalle"]["anotados_hoy"] == 0 and por_sede["lavalle"]["llamados"] == 1
    assert por_sede["media-agua"]["camiones"] == []


def test_la_hora_del_dia_es_la_de_san_juan():
    # 02:00 UTC del 29 son las 23:00 del 28 en San Juan: no cuenta como de hoy.
    tarde = viaje("chimbas", "descargado", registrado=datetime(2026, 10, 29, 2, 0, tzinfo=UTC))
    assert armar_tablero([tarde], HOY, ["chimbas"])["sedes"][0]["anotados_hoy"] == 0


def test_exige_permiso_y_avisa_si_no_esta_conectado(monkeypatch):
    monkeypatch.setattr(tablero_fila, "_dsn", "")
    app = FastAPI()
    app.include_router(tablero_fila.router)
    cliente = TestClient(app)
    assert cliente.get("/fila-tablero", headers={"X-Perfil-Simulado": "MEDICO"}).status_code == 403
    assert cliente.get("/fila-tablero", headers={"X-Perfil-Simulado": "BODEGA"}).status_code == 503


def test_turnos_exige_permiso_y_conexion(monkeypatch):
    monkeypatch.setattr(tablero_fila, "_dsn", "")
    app = FastAPI()
    app.include_router(tablero_fila.turnos)
    cliente = TestClient(app)
    parametros = {"sede": "chimbas", "mes": "2026-10"}
    assert cliente.get("/turnos-bodega/mes", params=parametros,
                       headers={"X-Perfil-Simulado": "MEDICO"}).status_code == 403
    assert cliente.get("/turnos-bodega/mes", params=parametros,
                       headers={"X-Perfil-Simulado": "BODEGA"}).status_code == 503
    assert cliente.post("/turnos-bodega", headers={"X-Perfil-Simulado": "BODEGA"}, json={
        "sede": "chimbas", "fecha": "2026-11-02", "cuit": "abc", "camiones": 1, "kg_por_camion": 11000,
    }).status_code == 422


def test_busca_camiones_por_patente_y_devuelve_el_ultimo_chofer(monkeypatch):
    consultas = []

    def leer(consulta, parametros):
        consultas.append(parametros)
        return [{"patente": "AB123CD", "patente_acoplado": "AC456EF", "ultimo_chofer_dni": "30111222",
                 "ultimo_chofer_nombre": "Juan Pérez", "ultimo_clientecuit": "20123456789",
                 "razonsocial": "Finca Los Álamos"}]

    monkeypatch.setattr(tablero_fila, "_leer", leer)
    app = FastAPI()
    app.include_router(tablero_fila.recepcion)
    cliente = TestClient(app)
    bascula = {"X-Perfil-Simulado": "BASCULA"}
    assert cliente.get("/recepcion-datos/vehiculos?q=a", headers=bascula).json() == []
    respuesta = cliente.get("/recepcion-datos/vehiculos?q=ab 12", headers=bascula).json()
    assert consultas == [{"patente": "AB12%"}]
    assert respuesta == [{"patente": "AB123CD", "patente_acoplado": "AC456EF", "chofer_dni": "30111222",
                          "chofer_nombre": "Juan Pérez", "productor_cuit": "20123456789",
                          "productor": "Finca Los Álamos"}]
    assert cliente.get("/recepcion-datos/vehiculos?q=ab12",
                       headers={"X-Perfil-Simulado": "MEDICO"}).status_code == 403
