import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from suite_juviar.modulos.activos.api.app import crear_router
from suite_juviar.modulos.activos.infrastructure.zebra import ConfiguracionEtiqueta, etiqueta_zpl


class ImpresoraFalsa:
    def __init__(self):
        self.enviados: list[tuple[str, int, str]] = []

    def __call__(self, direccion, puerto):
        self._destino = (direccion, puerto)
        return self

    def enviar(self, zpl):
        self.enviados.append((*self._destino, zpl))


def cliente(perfil="MANTENIMIENTO", impresora=None, ruta=None):
    ruta = ruta or str(Path(tempfile.mkdtemp()) / "modulos.sqlite3")
    app = FastAPI()
    app.include_router(crear_router("prueba", ruta, impresora or ImpresoraFalsa()), prefix="/activos")
    return TestClient(app, headers={"X-Perfil-Simulado": perfil, "X-Actor-Simulado": "operario"})


def preparar(c):
    bomba = c.post("/activos/tipos", json={"nombre": "Bombas", "prefijo": "bom"}).json()
    mueble = c.post("/activos/tipos", json={"nombre": "Muebles", "prefijo": "MUE"}).json()
    molienda = c.post("/activos/sectores", json={"nombre": "Molienda"}).json()
    bodega = c.post("/activos/sectores", json={"nombre": "Bodega"}).json()
    return bomba, mueble, molienda, bodega


def test_codigos_correlativos_por_tipo_y_sin_repetir():
    c = cliente()
    bomba, mueble, molienda, _ = preparar(c)
    codigos = [c.post("/activos/equipos", json={"tipo_id": t["id"], "sector_id": molienda["id"],
                                                 "descripcion": "x"}).json()["codigo"]
               for t in (bomba, bomba, mueble)]
    assert codigos == ["BOM-0001", "BOM-0002", "MUE-0001"]


def test_tipos_y_sectores_no_se_duplican_ni_se_borran_en_uso():
    c = cliente()
    bomba, _, molienda, _ = preparar(c)
    assert c.post("/activos/tipos", json={"nombre": "bombas", "prefijo": "BBA"}).status_code == 400
    assert c.post("/activos/tipos", json={"nombre": "Motores", "prefijo": "BOM"}).status_code == 400
    assert c.post("/activos/tipos", json={"nombre": "Motores", "prefijo": "M1"}).status_code == 400
    c.post("/activos/equipos", json={"tipo_id": bomba["id"], "sector_id": molienda["id"], "descripcion": "x"})
    assert c.delete(f"/activos/tipos/{bomba['id']}").status_code == 400
    assert c.delete(f"/activos/sectores/{molienda['id']}").status_code == 400
    assert c.put(f"/activos/tipos/{bomba['id']}", json={"nombre": "Bombas", "prefijo": "BMB"}).status_code == 400
    assert c.put(f"/activos/tipos/{bomba['id']}", json={"nombre": "Bombas de agua", "prefijo": "BOM"}).status_code == 200


def test_traslados_y_reparaciones_quedan_en_el_historial_con_costo_acumulado():
    c = cliente()
    bomba, _, molienda, bodega = preparar(c)
    codigo = c.post("/activos/equipos", json={"tipo_id": bomba["id"], "sector_id": molienda["id"],
                                              "descripcion": "Bomba centrífuga"}).json()["codigo"]

    assert c.post(f"/activos/equipos/{codigo}/traslado", json={"sector_id": bodega["id"]}).json()["sector"] == "Bodega"
    assert c.post(f"/activos/equipos/{codigo}/traslado", json={"sector_id": bodega["id"]}).status_code == 400

    for costo in (1000, 2500.5):
        assert c.post(f"/activos/equipos/{codigo}/taller",
                      json={"taller": "Taller Pérez", "motivo": "Pierde agua"}).status_code == 200
        # En taller no se puede trasladar ni volver a enviar.
        assert c.post(f"/activos/equipos/{codigo}/traslado", json={"sector_id": molienda["id"]}).status_code == 400
        assert c.post(f"/activos/equipos/{codigo}/taller", json={"taller": "Otro", "motivo": "x"}).status_code == 400
        assert c.post(f"/activos/equipos/{codigo}/regreso",
                      json={"costo": costo, "trabajo_realizado": "Sellos", "sector_id": molienda["id"]}).status_code == 200

    assert c.post(f"/activos/equipos/{codigo}/regreso", json={"costo": 1, "sector_id": molienda["id"]}).status_code == 400
    ficha = c.get(f"/activos/equipos/{codigo.lower()}").json()  # el lector puede mandar minúsculas
    assert (ficha["reparaciones"], ficha["costo_reparaciones"], ficha["estado"]) == (2, 3500.5, "EN_PLANTA")
    assert [m["tipo"] for m in ficha["historial"]][::-1] == [
        "ALTA", "TRASLADO", "SALIDA_TALLER", "REGRESO_TALLER", "SALIDA_TALLER", "REGRESO_TALLER"]
    assert ficha["historial"][-2]["hacia_sector"] == "Bodega"


def test_listado_con_los_mas_reparados_primero_y_busqueda():
    c = cliente()
    bomba, _, molienda, _ = preparar(c)
    a, b = (c.post("/activos/equipos", json={"tipo_id": bomba["id"], "sector_id": molienda["id"],
                                             "descripcion": d, "marca": "Grundfos"}).json()["codigo"]
            for d in ("Bomba vieja", "Bomba nueva"))
    c.post(f"/activos/equipos/{b}/taller", json={"taller": "T", "motivo": "m"})
    c.post(f"/activos/equipos/{b}/regreso", json={"costo": 10, "sector_id": molienda["id"]})
    assert [f["codigo"] for f in c.get("/activos/equipos").json()] == [a, b]
    assert [f["codigo"] for f in c.get("/activos/equipos?mas_reparados=true").json()] == [b, a]
    assert [f["codigo"] for f in c.get("/activos/equipos?texto=nueva").json()] == [b]
    assert len(c.get("/activos/equipos?texto=grundfos").json()) == 2
    assert c.get("/activos/equipos/BOM-9999").status_code == 404


def test_imprime_por_red_solo_con_impresora_cargada_por_un_administrador():
    impresora = ImpresoraFalsa()
    ruta = str(Path(tempfile.mkdtemp()) / "modulos.sqlite3")
    c = cliente(impresora=impresora, ruta=ruta)
    bomba, _, molienda, _ = preparar(c)
    codigo = c.post("/activos/equipos", json={"tipo_id": bomba["id"], "sector_id": molienda["id"],
                                              "descripcion": "Bomba ^XZ trucha"}).json()["codigo"]
    assert c.post(f"/activos/equipos/{codigo}/etiqueta", json={}).status_code == 409
    assert c.put("/activos/impresora", json={"direccion": "192.168.1.50"}).status_code == 403

    admin = cliente("SUPERADMIN", impresora, ruta)
    assert admin.put("/activos/impresora", json={"direccion": "8.8.8.8"}).status_code == 400
    assert admin.put("/activos/impresora", json={"direccion": "192.168.1.50", "dpi": 300}).status_code == 200

    assert c.post(f"/activos/equipos/{codigo}/etiqueta", json={"copias": 2}).json() == {"ok": True, "copias": 2}
    direccion, puerto, zpl = impresora.enviados[0]
    assert (direccion, puerto) == ("192.168.1.50", 9100)
    assert f"^FD{codigo}^FS" in zpl and "^BCN" in zpl and "^PQ2" in zpl
    assert zpl.count("^XZ") == 1  # el texto cargado no puede cortar la etiqueta


def test_otros_perfiles_no_entran():
    assert cliente("RRHH").get("/activos/equipos").status_code == 403


@pytest.mark.parametrize("dpi", [203, 300])
def test_etiqueta_respeta_el_tamano_configurado(dpi):
    zpl = etiqueta_zpl("BOM-0001", "Bomba", "Bombas", ConfiguracionEtiqueta("10.0.0.5", dpi=dpi, ancho_mm=100,
                                                                             alto_mm=50))
    assert f"^PW{round(100 * dpi / 25.4)}" in zpl
    assert f"^LL{round(50 * dpi / 25.4)}" in zpl


@pytest.mark.parametrize("direccion,puerto", [
    ("169.254.169.254", 9100), ("127.0.0.1", 9100), ("::ffff:192.168.1.5", 9100), ("fd00::1", 9100),
    ("100.64.0.1", 9100), ("192.168.1.50", 22), ("192.168.1.50", 5432),
])
def test_la_impresora_solo_puede_ser_una_zebra_de_la_red_interna(direccion, puerto):
    with pytest.raises(ValueError):
        ConfiguracionEtiqueta(direccion, puerto)
