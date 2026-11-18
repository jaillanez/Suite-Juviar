import base64
import tempfile
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from suite_juviar.modulos.activos.api.app import crear_router
from suite_juviar.modulos.activos.domain.puertos import MensajeEntrante, Salida

ENCARGADO = {"X-Perfil-Simulado": "ENCARGADO_MANTENIMIENTO", "X-Actor-Simulado": "encargado"}
ADMIN = {"X-Perfil-Simulado": "SUPERADMIN", "X-Actor-Simulado": "admin"}


def _png() -> str:
    salida = BytesIO()
    Image.new("RGB", (300, 100), "white").save(salida, "PNG")
    return "data:image/png;base64," + base64.b64encode(salida.getvalue()).decode()


FIRMA = _png()


class PuertaFalsa:
    def __init__(self):
        self.publicados, self.anulados, self.salieron, self.entrantes = {}, [], {}, []

    def publicar(self, remito):
        self.publicados[remito.id] = remito

    def anular(self, remito_id, actor):
        if remito_id in self.salieron:
            raise ValueError("ese remito ya salió de la planta")
        self.anulados.append(remito_id)

    def salidas(self, ids):
        return {i: self.salieron[i] for i in ids if i in self.salieron}

    def tomar_mensajes(self):
        return list(self.entrantes)

    def confirmar_mensajes(self, ids):
        self.entrantes = [m for m in self.entrantes if m.id not in ids]


def cliente(perfil="MANTENIMIENTO"):
    puerta = PuertaFalsa()
    app = FastAPI()
    app.include_router(crear_router("prueba", str(Path(tempfile.mkdtemp()) / "m.sqlite3"), puerta=puerta),
                       prefix="/activos")
    c = TestClient(app, headers={"X-Perfil-Simulado": perfil, "X-Actor-Simulado": "operario"})
    tipo = c.post("/activos/tipos", json={"nombre": "Bombas", "prefijo": "BOM"}).json()
    sector = c.post("/activos/sectores", json={"nombre": "Molienda", "bodega": "chimbas"}).json()
    bomba = c.post("/activos/equipos", json={"tipo_id": tipo["id"], "descripcion": "Bomba de trasiego",
                                             "sector_id": sector["id"]}).json()
    return c, puerta, bomba, sector


def remito(c, items=None, **extra):
    datos = {"bodega": "chimbas", "destino": "Taller Pérez", "motivo": "Bobinado del motor",
             "items": items or [{"codigo": "BOM-0001"}, {"descripcion": "Amoladora Bosch"}], **extra}
    return c.post("/activos/remitos", json=datos)


def test_nada_sale_sin_la_firma_del_encargado_y_la_guardia_ve_lo_firmado():
    c, puerta, _, _ = cliente()
    r = remito(c).json()
    assert r["estado"] == "BORRADOR" and r["items"][0]["descripcion"] == "Bomba de trasiego"
    assert c.post(f"/activos/remitos/{r['id']}/firma", json={"modo": "papel"}).status_code == 403
    assert puerta.publicados == {}
    firmado = c.post(f"/activos/remitos/{r['id']}/firma", json={"modo": "papel"}, headers=ENCARGADO).json()
    assert firmado["estado"] == "AUTORIZADO" and firmado["firma"]["por"] == "encargado"
    assert r["id"] in puerta.publicados
    assert c.put(f"/activos/remitos/{r['id']}", json={"bodega": "chimbas", "destino": "Otro", "motivo": "x",
                                                     "items": [{"descripcion": "y"}]}).status_code == 400


def test_firma_en_celular_exige_la_imagen_y_sale_en_el_pdf():
    c, _, _, _ = cliente()
    r = remito(c).json()
    sin = c.post(f"/activos/remitos/{r['id']}/firma", json={"modo": "celular"}, headers=ENCARGADO)
    assert sin.status_code == 400
    ok = c.post(f"/activos/remitos/{r['id']}/firma", json={"modo": "celular", "imagen": FIRMA}, headers=ENCARGADO)
    assert ok.json()["firma"]["modo"] == "celular"
    assert "imagen" not in ok.json()["firma"]
    pdf = c.get(f"/activos/remitos/{r['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert 'remito-000001.pdf' in pdf.headers["content-disposition"]


def test_la_salida_de_la_guardia_pasa_los_equipos_a_taller_y_se_controla_el_regreso():
    c, puerta, _, sector = cliente()
    r = remito(c).json()
    c.post(f"/activos/remitos/{r['id']}/firma", json={"modo": "papel"}, headers=ENCARGADO)
    puerta.salieron[r["id"]] = Salida(datetime.now(UTC), "guardia:juan")
    afuera = c.get("/activos/remitos").json()[0]
    assert afuera["estado"] == "AFUERA" and afuera["salio_por"] == "guardia:juan" and afuera["afuera"] == 2
    assert c.get("/activos/equipos/BOM-0001").json()["estado"] == "EN_TALLER"
    # Un equipo en taller no puede ir en otro remito.
    assert remito(c, [{"codigo": "BOM-0001"}]).status_code == 400
    # La herramienta sin código vuelve con un clic; el equipo, con su costo.
    assert c.post(f"/activos/remitos/{r['id']}/items/0/regreso").status_code == 400
    c.post(f"/activos/remitos/{r['id']}/items/1/regreso")
    vuelta = c.post(f"/activos/remitos/{r['id']}/equipos/BOM-0001/regreso",
                    json={"costo": 15000, "trabajo_realizado": "Bobinado", "sector_id": sector["id"],
                          "empresa": "ENAV"}).json()
    assert vuelta["estado"] == "CERRADO"
    assert c.get("/activos/equipos/BOM-0001").json()["costo_reparaciones"] == 15000


def test_regreso_cargado_desde_la_ficha_tambien_cierra_el_remito():
    c, puerta, _, sector = cliente()
    r = remito(c, [{"codigo": "BOM-0001"}]).json()
    c.post(f"/activos/remitos/{r['id']}/firma", json={"modo": "papel"}, headers=ENCARGADO)
    puerta.salieron[r["id"]] = Salida(datetime.now(UTC), "guardia:juan")
    c.get("/activos/remitos")
    c.post("/activos/equipos/BOM-0001/regreso", json={"costo": 0, "sector_id": sector["id"], "empresa": "JUBIAR"})
    assert c.get(f"/activos/remitos/{r['id']}").json()["estado"] == "CERRADO"


def test_demorado_segun_los_dias_de_parametros():
    c, puerta, _, _ = cliente()
    r = remito(c, [{"descripcion": "Taladro"}]).json()
    c.post(f"/activos/remitos/{r['id']}/firma", json={"modo": "papel"}, headers=ENCARGADO)
    puerta.salieron[r["id"]] = Salida(datetime.now(UTC) - timedelta(days=10), "guardia:juan")
    assert c.get("/activos/remitos").json()[0]["demorado"] is False  # sin días cargados no hay aviso
    assert c.put("/activos/parametros-remitos", json={"dias_maximos_fuera": 7, "modo_whatsapp": "revision"}
                 ).status_code == 403
    c.put("/activos/parametros-remitos", json={"dias_maximos_fuera": 7, "modo_whatsapp": "revision"}, headers=ADMIN)
    assert c.get("/activos/remitos").json()[0]["demorado"] is True


def test_anular_antes_de_salir_avisa_a_la_guardia_y_despues_no_se_puede():
    c, puerta, _, _ = cliente()
    r = remito(c).json()
    c.post(f"/activos/remitos/{r['id']}/firma", json={"modo": "papel"}, headers=ENCARGADO)
    assert c.post(f"/activos/remitos/{r['id']}/anular", json={"motivo": "Se arregla en planta"},
                  headers=ENCARGADO).json()["estado"] == "ANULADO"
    assert puerta.anulados == [r["id"]]
    otro = remito(c).json()  # la bomba quedó libre
    c.post(f"/activos/remitos/{otro['id']}/firma", json={"modo": "papel"}, headers=ENCARGADO)
    puerta.salieron[otro["id"]] = Salida(datetime.now(UTC), "guardia:juan")
    assert c.post(f"/activos/remitos/{otro['id']}/anular", json={"motivo": "x"}, headers=ENCARGADO).status_code == 400


def test_whatsapp_en_revision_queda_en_la_bandeja_y_directo_arma_el_borrador():
    c, puerta, _, _ = cliente()
    puerta.entrantes = [MensajeEntrante("1", "5492644000001", "Pedro", "Sale BOM-0001 a taller de Chimbas",
                                        datetime.now(UTC), b"\xff\xd8" + b"0" * 2000, "image/jpeg")]
    mensajes = c.get("/activos/mensajes-whatsapp").json()
    assert mensajes[0]["pendiente"] and mensajes[0]["con_foto"] and puerta.entrantes == []
    assert c.get("/activos/remitos").json() == []
    armado = c.post(f"/activos/mensajes-whatsapp/{mensajes[0]['id']}/remito").json()
    assert armado["items"][0]["codigo"] == "BOM-0001" and armado["bodega"] == "chimbas" and armado["con_foto"]
    assert armado["estado"] == "BORRADOR" and armado["origen"] == "whatsapp"
    # Falta el destino: no se puede firmar hasta completarlo.
    assert c.post(f"/activos/remitos/{armado['id']}/firma", json={"modo": "papel"}, headers=ENCARGADO).status_code == 400

    c.put("/activos/parametros-remitos", json={"dias_maximos_fuera": None, "modo_whatsapp": "directo"}, headers=ADMIN)
    puerta.entrantes = [MensajeEntrante("2", "5492644000001", "Pedro", "Se lleva la soldadora", datetime.now(UTC))]
    c.get("/activos/mensajes-whatsapp")
    directos = [x for x in c.get("/activos/remitos").json() if x["origen"] == "whatsapp"]
    assert len(directos) == 2 and directos[0]["items"][0]["descripcion"] == "Se lleva la soldadora"


def test_validaciones_y_permisos():
    c, _, _, _ = cliente()
    assert remito(c, [{"codigo": "NO-9999"}]).status_code == 404
    assert remito(c, bodega="mendoza").status_code == 400
    assert remito(c, items=[{"codigo": "BOM-0001"}, {"codigo": "BOM-0001"}]).status_code == 400
    assert c.post("/activos/remitos", json={"bodega": "chimbas", "destino": "x", "motivo": "y", "items": []}
                  ).status_code == 422
    r = remito(c).json()
    malo = c.post("/activos/equipos/BOM-0001/regreso", json={"costo": -1, "sector_id": "x", "empresa": "ENAV"})
    assert malo.status_code == 422
    assert c.post(f"/activos/remitos/{r['id']}/firma", json={"modo": "celular", "imagen": "no-es-base64!"},
                  headers=ENCARGADO).status_code == 400
    assert c.get("/activos/remitos", headers={"X-Perfil-Simulado": "COMPRAS"}).status_code == 403
