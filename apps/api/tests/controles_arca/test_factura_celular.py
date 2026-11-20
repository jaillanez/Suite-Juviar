"""Factura desde el celular: QR de ARCA, lectura de la foto sin QR, foto adjunta y permisos."""

import base64
import json
from datetime import date
from urllib.parse import quote

import pytest

from suite_juviar.modulos.controles_arca.domain.lectura import (
    QRInvalido,
    extraer_datos,
    leer_qr,
    tipo_imagen,
    validar_foto,
)
from suite_juviar.modulos.controles_arca.infrastructure import lector as lector_facturas

from .test_controles_arca import CAE, ENAV, PROVEEDOR, Conector, cliente, configurado, servicio

JPEG = b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF" + b"0" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 50
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"0" * 50
FOTO = base64.b64encode(JPEG).decode()
AJENO = "30712345671"  # CUIT válido que no es de ninguna de las dos empresas


def datos_qr(**cambios):
    return {"ver": 1, "fecha": "2026-11-10", "cuit": int(PROVEEDOR), "ptoVta": 3, "tipoCmp": 1, "nroCmp": 1234,
            "importe": 12100.5, "moneda": "PES", "ctz": 1, "tipoDocRec": 80, "nroDocRec": int(ENAV),
            "tipoCodAut": "E", "codAut": int(CAE), **cambios}


def url_qr(datos=None, host="www.afip.gob.ar", segura=False, relleno=True, crudo=None, codificada=False):
    contenido = crudo if crudo is not None else json.dumps(datos or datos_qr()).encode()
    texto = (base64.urlsafe_b64encode if segura else base64.b64encode)(contenido).decode()
    if not relleno:
        texto = texto.rstrip("=")
    if codificada:
        texto = quote(texto, safe="")
    return f"https://{host}/fe/qr/?p={texto}"


# --- Decodificador del QR ----------------------------------------------------

def test_qr_de_arca_se_lee_en_todas_sus_variantes():
    qr = leer_qr(url_qr())
    assert (qr.cuit_emisor, qr.punto_venta, qr.tipo_comprobante, qr.numero) == (PROVEEDOR, 3, 1, 1234)
    assert (qr.fecha, qr.importe_total, qr.autorizacion, qr.codigo_autorizacion) == (date(2026, 11, 10), 12100.5, "CAE", CAE)
    assert qr.nro_doc_receptor == ENAV
    # Base64 con alfabeto de URL, sin relleno, con «+» y «/» crudos, y el sitio nuevo de ARCA.
    rara = datos_qr(nroCmp=99_999_999, importe=1.5, extra="~~~>>>???")
    assert "+" in base64.b64encode(json.dumps(rara).encode()).decode() or "/" in base64.b64encode(
        json.dumps(rara).encode()).decode()
    for url in (url_qr(rara), url_qr(rara, segura=True), url_qr(rara, relleno=False),
                url_qr(rara, segura=True, relleno=False), url_qr(rara, host="www.arca.gob.ar"),
                url_qr(rara, host="afip.gob.ar"), url_qr(rara, codificada=True)):
        assert leer_qr(url).numero == 99_999_999, url
    # Hay emisores que mandan los números como texto, y el CAEA va con «A».
    qr = leer_qr(url_qr(datos_qr(cuit=PROVEEDOR, ptoVta="3", codAut=CAE, tipoCodAut="A", importe="100.25")))
    assert (qr.autorizacion, qr.punto_venta, qr.importe_total) == ("CAEA", 3, 100.25)
    # Consumidor final: sin receptor.
    assert leer_qr(url_qr(datos_qr(tipoDocRec=99, nroDocRec=0))).nro_doc_receptor == ""


@pytest.mark.parametrize("texto", [
    "", "hola", "https://www.afip.gob.ar/fe/qr/",
    url_qr().replace("https://", "http://"),
    url_qr(host="www.afip.gob.ar.sitio-falso.com"),
    url_qr(host="afip.gob.ar.com"),
    url_qr(host="falsoafip.gob.ar"),
    url_qr(host="usuario@www.afip.gob.ar"),
    url_qr(host="www.afip.gob.ar:8443"),
    url_qr().replace("/fe/qr/", "/otra/"),
    url_qr() + "&p=otro",
    url_qr(crudo=b"no es json"),
    url_qr(crudo=b"[1, 2]"),
    url_qr(crudo=b"\xff\xfe"),
    "https://www.afip.gob.ar/fe/qr/?p=%%%",
    "https://www.afip.gob.ar/fe/qr/?p=A",
    "https://www.afip.gob.ar/fe/qr/?p=" + "A" * 3000,
    url_qr(datos_qr(ver=2)),
    url_qr(datos_qr(cuit=30693135670)),
    url_qr(datos_qr(cuit=123)),
    url_qr(datos_qr(ptoVta=0)), url_qr(datos_qr(ptoVta=100000)),
    url_qr(datos_qr(nroCmp=0)), url_qr(datos_qr(nroCmp=True)),
    url_qr(datos_qr(importe=0)), url_qr(datos_qr(importe=-5)), url_qr(datos_qr(importe=1e13)),
    url_qr(datos_qr(importe="1,5")), url_qr(datos_qr(importe=None)),
    url_qr(datos_qr(fecha="10/11/2026")), url_qr(datos_qr(fecha="2026-02-30")), url_qr(datos_qr(fecha=20261110)),
    url_qr(datos_qr(moneda="pesos")), url_qr(datos_qr(tipoCodAut="X")), url_qr(datos_qr(tipoCodAut=None)),
    url_qr(datos_qr(codAut=1234)), url_qr(datos_qr(codAut="7123456789012a")),
    url_qr({k: v for k, v in datos_qr().items() if k != "cuit"}),
])
def test_qr_que_no_es_de_arca_o_trae_datos_malos_se_rechaza(texto):
    with pytest.raises(QRInvalido):
        leer_qr(texto)


def test_el_nan_del_importe_no_pasa():
    # json.dumps escribe NaN e Infinity y json.loads los acepta: el QR igual se rechaza.
    for valor in (float("nan"), float("inf")):
        with pytest.raises(QRInvalido):
            leer_qr(url_qr(datos_qr(importe=valor)))


# --- Foto y lectura sin QR -----------------------------------------------------

def test_tipo_de_foto_por_sus_bytes_y_tope_de_tamano():
    assert (tipo_imagen(JPEG), tipo_imagen(PNG), tipo_imagen(WEBP)) == ("image/jpeg", "image/png", "image/webp")
    assert tipo_imagen(b"%PDF-1.4") is None and tipo_imagen(b"GIF89a") is None and tipo_imagen(b"") is None
    assert tipo_imagen(b"RIFF\x00\x00\x00\x00WAVE") is None
    for malo in (b"", b"<svg onload=alert(1)>", b"%PDF-1.4", JPEG[:3] + b"\x00" * (2 * 1024 * 1024)):
        with pytest.raises(ValueError):
            validar_foto(malo)
    assert validar_foto(JPEG) == "image/jpeg"


TEXTO_FACTURA = """
ORIGINAL  A  FACTURA  COD. 01
Proveedor SA  CUIT: 30-69313567-9
Punto de Venta: 00003 Comp. Nro: 00001234
Fecha de Emisión: 10/11/2026
Cliente: ENAV S.A. CUIT 30546689979
Subtotal: $ 10.000,00
Importe Total: $ 12.100,50
CAE N°: 71234567890123  Fecha de Vto. de CAE: 20/11/2026
"""


def test_extraccion_con_reglas_del_texto_de_la_foto():
    datos = extraer_datos(TEXTO_FACTURA, {"ENAV": ENAV, "JUBIAR": ""}, date(2026, 11, 18))
    assert datos == {"empresa": "ENAV", "cuit_emisor": PROVEEDOR, "tipo_comprobante": 1, "punto_venta": 3,
                     "numero": 1234, "fecha": date(2026, 11, 10), "importe_total": 12100.5,
                     "autorizacion": "CAE", "codigo_autorizacion": CAE}
    # Otra forma común: «0003-00001234», «FACTURA B», total sin «importe».
    otro = "FACTURA B 0003-00001234 CUIT 30693135679 12/11/2026 TOTAL $ 999,90"
    datos = extraer_datos(otro, {"ENAV": ENAV, "JUBIAR": ""}, date(2026, 11, 18))
    assert (datos["tipo_comprobante"], datos["punto_venta"], datos["numero"], datos["importe_total"]) == (6, 3, 1234, 999.9)
    assert datos["empresa"] is None and datos["autorizacion"] is None
    # Nada legible: todo vacío para cargar a mano. Una fecha futura no se propone.
    assert set(extraer_datos("", {"ENAV": "", "JUBIAR": ""}, date(2026, 11, 18)).values()) == {None}
    assert extraer_datos("Fecha 25/12/2026", {"ENAV": "", "JUBIAR": ""}, date(2026, 11, 18))["fecha"] is None


class Lector:
    def __init__(self, texto=TEXTO_FACTURA, ia_externa=False, falla=None):
        self.texto, self.ia_externa, self.falla, self.leidas = texto, ia_externa, falla, []

    def leer(self, contenido, tipo):
        self.leidas.append(tipo)
        if self.falla:
            raise self.falla
        return self.texto, "ocr"


def preparado(lector=None):
    conector = Conector()
    s = servicio(conector)
    s.lector = lector or Lector()
    configurado(s)
    return s, conector


# --- API ---------------------------------------------------------------------

def test_con_qr_da_de_alta_controla_guarda_la_foto_y_no_duplica():
    s, conector = preparado()
    c = cliente("ADMINISTRACION", s)
    r = c.post("/controles-arca/celular/qr", json={"qr": url_qr(), "foto_base64": FOTO})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["estado"] == "listo" and cuerpo["ya_cargada"] is False
    factura = cuerpo["factura"]
    assert (factura["empresa"], factura["comprobante"], factura["autorizacion"]) == ("ENAV", "Factura A 00003-00001234", "CAE")
    assert factura["controlada"] and factura["tiene_foto"]
    assert {x["numero"]: x["estado"] for x in factura["controles"]} == {1: "pendiente", 2: "ok", 3: "ok", 4: "ok", 5: "ok"}
    assert conector.receptor == ENAV and len(conector.llamadas) == 2
    foto = c.get(f"/controles-arca/facturas/{factura['id']}/foto")
    assert foto.status_code == 200 and foto.content == JPEG and foto.headers["content-type"] == "image/jpeg"
    assert foto.headers["x-content-type-options"] == "nosniff"
    # Misma factura otra vez (aunque sea otra foto): se muestra la cargada, sin consultar ARCA de nuevo.
    otra = c.post("/controles-arca/celular/qr", json={"qr": url_qr(segura=True), "foto_base64": base64.b64encode(PNG).decode()})
    assert otra.json()["ya_cargada"] is True and otra.json()["factura"]["id"] == factura["id"]
    assert len(conector.llamadas) == 2 and len(s.repo.facturas) == 1
    assert c.get(f"/controles-arca/facturas/{factura['id']}/foto").content == JPEG
    # Queda en la lista de Gestión igual que una cargada desde la computadora.
    assert [f["id"] for f in c.get("/controles-arca/facturas").json()] == [factura["id"]]


def test_si_el_receptor_del_qr_no_es_del_grupo_elige_el_usuario():
    s, conector = preparado()
    c = cliente("ADMINISTRACION", s)
    qr = url_qr(datos_qr(nroDocRec=int(AJENO)))
    r = c.post("/controles-arca/celular/qr", json={"qr": qr, "foto_base64": FOTO}).json()
    assert r["estado"] == "elegir_empresa" and r["datos"]["numero"] == 1234 and r["datos"]["nro_doc_receptor"] == AJENO
    assert not s.repo.facturas and not conector.llamadas
    r = c.post("/controles-arca/celular/qr", json={"qr": qr, "foto_base64": FOTO, "empresa": "JUBIAR"}).json()
    assert r["estado"] == "listo" and r["factura"]["empresa"] == "JUBIAR"
    # Si el receptor sí es del grupo, manda el QR aunque el usuario haya elegido otra.
    r = c.post("/controles-arca/celular/qr", json={"qr": url_qr(datos_qr(nroCmp=5)), "foto_base64": FOTO,
                                                   "empresa": "JUBIAR"}).json()
    assert r["factura"]["empresa"] == "ENAV"


def test_qr_malo_o_foto_mala_no_carga_nada():
    s, conector = preparado()
    c = cliente("ADMINISTRACION", s)
    malo = c.post("/controles-arca/celular/qr", json={"qr": url_qr(host="afip.gob.ar.evil.com"), "foto_base64": FOTO})
    assert malo.status_code == 400 and "ARCA" in malo.json()["detail"]
    for foto, esperado in ((base64.b64encode(b"%PDF-1.4").decode(), 400), ("%%%", 400),
                           (base64.b64encode(b"<svg/>").decode(), 400),
                           (base64.b64encode(JPEG[:4] + b"0" * (2 * 1024 * 1024)).decode(), 400)):
        for ruta, cuerpo in (("qr", {"qr": url_qr()}), ("leer", {})):
            r = c.post(f"/controles-arca/celular/{ruta}", json={**cuerpo, "foto_base64": foto})
            assert r.status_code == esperado, (ruta, r.text[:200])
    futura = c.post("/controles-arca/celular/qr", json={"qr": url_qr(datos_qr(fecha="2027-01-01")), "foto_base64": FOTO})
    assert futura.status_code == 400
    otro_tipo = c.post("/controles-arca/celular/qr", json={"qr": url_qr(datos_qr(tipoCmp=999)), "foto_base64": FOTO})
    assert otro_tipo.status_code == 400
    assert not s.repo.facturas and not conector.llamadas
    assert c.get("/controles-arca/facturas/no-existe/foto").status_code == 404


def test_sin_qr_propone_datos_y_no_controla_hasta_confirmar():
    lector = Lector()
    s, conector = preparado(lector)
    c = cliente("ADMINISTRACION", s)
    r = c.post("/controles-arca/celular/leer", json={"foto_base64": FOTO})
    assert r.status_code == 200, r.text
    propuesta = r.json()
    assert propuesta["datos"]["cuit_emisor"] == PROVEEDOR and propuesta["datos"]["codigo_autorizacion"] == CAE
    assert propuesta["texto_detectado"] and lector.leidas == ["image/jpeg"]
    # Leer no da de alta ni consulta ARCA.
    assert not s.repo.facturas and not conector.llamadas
    datos = {k: v for k, v in propuesta["datos"].items()}
    datos["importe_total"] = 12100.75  # la persona corrigió el importe mirando el papel
    confirmada = c.post("/controles-arca/celular/confirmar", json={"factura": datos, "foto_base64": FOTO})
    assert confirmada.status_code == 200, confirmada.text
    factura = confirmada.json()["factura"]
    assert factura["importe_total"] == 12100.75 and factura["controlada"] and factura["tiene_foto"]
    assert len(conector.llamadas) == 2
    # Confirmar dos veces la misma no la duplica.
    again = c.post("/controles-arca/celular/confirmar", json={"factura": datos, "foto_base64": FOTO}).json()
    assert again["ya_cargada"] and len(s.repo.facturas) == 1 and len(conector.llamadas) == 2
    # El mismo CUIT escrito con guiones o espacios es la misma factura.
    c_guiones = str(datos["cuit_emisor"])
    c_guiones = f"{c_guiones[:2]}-{c_guiones[2:10]} -{c_guiones[10:]}"
    tercera = c.post("/controles-arca/celular/confirmar",
                     json={"factura": {**datos, "cuit_emisor": c_guiones}, "foto_base64": FOTO})
    assert tercera.status_code in (200, 422)
    if tercera.status_code == 200:
        assert tercera.json()["ya_cargada"] and len(s.repo.facturas) == 1
    assert s.buscar_factura(c_guiones, datos["tipo_comprobante"], datos["punto_venta"], datos["numero"]) is not None
    # Sin todos los datos confirmados no hay alta.
    incompleta = {**datos, "numero": 99, "cuit_emisor": None}
    assert c.post("/controles-arca/celular/confirmar", json={"factura": incompleta, "foto_base64": FOTO}).status_code == 422


def test_sin_qr_si_la_lectura_falla_igual_se_puede_cargar_a_mano():
    s, _ = preparado(Lector(falla=RuntimeError("La IA no pudo leer la factura.")))
    r = cliente("ADMINISTRACION", s).post("/controles-arca/celular/leer", json={"foto_base64": FOTO}).json()
    assert r["mensaje"] == "La IA no pudo leer la factura." and set(r["datos"].values()) == {None}
    s, _ = preparado(Lector(texto=""))
    r = cliente("ADMINISTRACION", s).post("/controles-arca/celular/leer", json={"foto_base64": FOTO}).json()
    assert not r["texto_detectado"] and "cargá los datos" in r["mensaje"]


def test_permisos_de_la_factura_desde_el_celular():
    s, _ = preparado()
    admin = cliente("ADMINISTRACION", s)
    fid = admin.post("/controles-arca/celular/qr", json={"qr": url_qr(), "foto_base64": FOTO}).json()["factura"]["id"]
    for perfil in ("RRHH", "COMERCIAL", "DEPOSITO", "MANTENIMIENTO"):
        otro = cliente(perfil, s)
        assert otro.post("/controles-arca/celular/qr", json={"qr": url_qr(datos_qr(nroCmp=9)), "foto_base64": FOTO}).status_code == 403
        assert otro.post("/controles-arca/celular/leer", json={"foto_base64": FOTO}).status_code == 403
        assert otro.post("/controles-arca/celular/confirmar", json={"factura": {}, "foto_base64": FOTO}).status_code == 403
        assert otro.get(f"/controles-arca/facturas/{fid}/foto").status_code == 403
    # Control negativo: con el permiso, la misma operación sí pasa.
    assert cliente("COMPRAS", s).get(f"/controles-arca/facturas/{fid}/foto").status_code == 200
    assert cliente("ADMINISTRACION", s).post(
        "/controles-arca/celular/qr", json={"qr": url_qr(datos_qr(nroCmp=9)), "foto_base64": FOTO}).status_code == 200
    assert len(s.repo.facturas) == 2


# --- Lector de fotos: IA externa sólo con autorización expresa ----------------

def test_la_foto_sale_a_la_ia_solo_con_clave_y_autorizacion(monkeypatch):
    enviadas = []
    monkeypatch.setattr(lector_facturas, "_leer_con_deepseek", lambda c, t, k: enviadas.append(t) or "texto ia")
    monkeypatch.setattr(lector_facturas, "leer_texto_imagen", lambda c, e: "texto ocr")
    monkeypatch.delenv("SJ_SALUD_IA_API_KEY", raising=False)
    monkeypatch.delenv("SJ_CONTROLES_ARCA_IA_EXTERNA_AUTORIZADA", raising=False)
    assert lector_facturas.LectorFacturasLocal().leer(JPEG, "image/jpeg") == ("texto ocr", "ocr")
    monkeypatch.setenv("SJ_SALUD_IA_API_KEY", "clave")
    sin_autorizar = lector_facturas.LectorFacturasLocal()
    assert not sin_autorizar.ia_externa and sin_autorizar.leer(JPEG, "image/jpeg") == ("texto ocr", "ocr")
    monkeypatch.setenv("SJ_CONTROLES_ARCA_IA_EXTERNA_AUTORIZADA", "no")
    assert not lector_facturas.LectorFacturasLocal().ia_externa
    assert not enviadas
    monkeypatch.setenv("SJ_CONTROLES_ARCA_IA_EXTERNA_AUTORIZADA", "si")
    autorizado = lector_facturas.LectorFacturasLocal()
    assert autorizado.ia_externa and autorizado.leer(JPEG, "image/jpeg") == ("texto ia", "deepseek")
    assert enviadas == ["image/jpeg"]
    monkeypatch.delenv("SJ_SALUD_IA_API_KEY")
    assert not lector_facturas.LectorFacturasLocal().ia_externa
    # El catálogo avisa a la pantalla si la foto saldría de la empresa.
    s, _ = preparado(Lector(ia_externa=True))
    assert cliente("ADMINISTRACION", s).get("/controles-arca/catalogo").json()["lectura_ia_externa"] is True
