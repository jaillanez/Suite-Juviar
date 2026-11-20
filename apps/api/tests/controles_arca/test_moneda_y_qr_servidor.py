"""Facturas en moneda extranjera y QR leído en el servidor cuando el celular no lo lee."""

import base64
import io
import pickle
import time
from dataclasses import fields

import pytest
import zxingcpp
from PIL import Image, ImageDraw, ImageFilter
from pypdf import PdfReader

from suite_juviar.modulos.controles_arca.domain.modelos import Control, Factura, importe_escrito
from suite_juviar.modulos.controles_arca.infrastructure.qr import LectorQRServidor
from suite_juviar.modulos.controles_arca.infrastructure.sqlite import ControlesSQLite

from .test_controles_arca import ALTA, CAE, PROVEEDOR, alta, cliente, servicio
from .test_factura_celular import AJENO, FOTO, Lector, datos_qr, preparado, url_qr

DOLARES = datos_qr(moneda="DOL", ctz=1524.5, importe=297.36)


# --- Moneda -------------------------------------------------------------------

def test_importe_en_pesos_y_en_moneda_extranjera():
    assert importe_escrito(12100.5) == "$ 12.100,50"
    assert importe_escrito(297.36, "DOL", 1524.5) == "USD 297,36 (≈ $ 453.325,32 a 1.524,50)"
    assert importe_escrito(10, "060", 1100.123) == "EUR 10,00 (≈ $ 11.001,23 a 1.100,123)"
    # Una moneda sin sigla conocida se muestra con el código de ARCA.
    assert importe_escrito(1, "012", 210) == "012 1,00 (≈ $ 210,00 a 210,00)"


def test_la_moneda_y_la_cotizacion_se_validan():
    s = servicio()
    for moneda, cotizacion in (("dol", 1500), ("DOLAR", 1500), ("D-L", 1500), ("DOL", 0), ("DOL", -1),
                               ("DOL", float("nan")), ("DOL", float("inf"))):
        with pytest.raises(ValueError):
            alta(s, moneda=moneda, cotizacion=cotizacion)
    # En pesos la cotización siempre es 1, venga lo que venga.
    assert alta(s, numero=2, moneda="PES", cotizacion=7).cotizacion == 1.0
    assert alta(s, numero=3).moneda == "PES"
    c = cliente("ADMINISTRACION", s)
    for cambio in ({"moneda": "dolar"}, {"moneda": "DOL", "cotizacion": 0}, {"moneda": "DOL", "cotizacion": "NaN"}):
        assert c.post("/controles-arca/facturas", json={**ALTA, **cambio}).status_code == 422, cambio
    euros = c.post("/controles-arca/facturas", json={**ALTA, "moneda": "060", "cotizacion": 1700, "importe_total": 10})
    assert euros.status_code == 201, euros.text
    assert (euros.json()["moneda"], euros.json()["cotizacion"], euros.json()["importe_pesos"]) == ("060", 1700, 17000)
    assert euros.json()["importe_texto"].startswith("EUR 10,00")
    assert c.get("/controles-arca/catalogo").json()["monedas"]["DOL"] == "Dólar estadounidense"


def test_factura_en_dolares_desde_el_qr_se_muestra_y_se_constata_en_dolares():
    s, conector = preparado()
    c = cliente("ADMINISTRACION", s)
    r = c.post("/controles-arca/celular/qr", json={"qr": url_qr(DOLARES), "foto_base64": FOTO})
    assert r.status_code == 200, r.text
    vista = r.json()["factura"]
    assert (vista["moneda"], vista["cotizacion"], vista["importe_total"]) == ("DOL", 1524.5, 297.36)
    assert vista["importe_pesos"] == 453325.32
    assert vista["importe_texto"] == "USD 297,36 (≈ $ 453.325,32 a 1.524,50)"
    assert c.get("/controles-arca/facturas").json()[0]["importe_texto"] == vista["importe_texto"]
    # A ARCA se le manda el importe en la moneda del comprobante, como lo confirmó.
    factura = s.obtener(vista["id"])
    assert factura.importe_total == 297.36 and len(conector.llamadas) == 2
    # La constancia en PDF dice la moneda y el equivalente en pesos.
    pdf = s.repo.archivos[f"{factura.id}:{int(Control.COMPROBANTE)}"]
    texto = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "USD 297,36" in texto and "453.325,32" in texto


def test_facturas_guardadas_antes_de_la_moneda_se_leen_en_pesos(tmp_path):
    """Regresión: en producción hay facturas guardadas con pickle sin moneda ni cotización.

    El pickle sólo lo escribe y lo lee el propio servidor (MapaSQLite); acá se arma uno igual.
    """
    nueva = alta(servicio())
    anteriores = [f.name for f in fields(Factura)][:-2]
    assert anteriores[-1] == "resultados"
    estado_viejo = [getattr(nueva, nombre) for nombre in anteriores]

    class FacturaVieja:
        """Arma el pickle tal como lo escribía la versión anterior de Factura."""

        def __reduce__(self):
            return object.__new__, (Factura,), estado_viejo

    leida = pickle.loads(pickle.dumps(FacturaVieja(), protocol=pickle.HIGHEST_PROTOCOL))
    assert (leida.moneda, leida.cotizacion, leida.importe_total) == ("PES", 1.0, nueva.importe_total)
    assert leida.importe_texto == "$ 121.000,50" and leida == nueva
    # Y pasando por la base, como en el servidor.
    repo = ControlesSQLite(tmp_path / "c.sqlite3")
    repo.facturas["vieja"] = FacturaVieja()
    assert repo.facturas["vieja"].moneda == "PES" and repo.facturas["vieja"].comprobante == nueva.comprobante
    # Las nuevas van y vuelven con todo.
    dolares = alta(servicio(), moneda="DOL", cotizacion=1524.5)
    assert pickle.loads(pickle.dumps(dolares)) == dolares
    with pytest.raises(ValueError):
        object.__new__(Factura).__setstate__([*estado_viejo, "PES", 1.0, "de más"])


# --- QR en el servidor --------------------------------------------------------

def imagen_qr(texto: str, modulo: int) -> Image.Image:
    codigo = zxingcpp.create_barcode(texto, zxingcpp.BarcodeFormat.QRCode)
    qr = Image.fromarray(zxingcpp.write_barcode_to_image(codigo, scale=1)).convert("L")
    return qr.resize((qr.width * modulo, qr.height * modulo), Image.Resampling.NEAREST)


def hoja_con_qr(texto: str, modulo: int = 5, desenfoque: float = 0.0, lugar=(150, 2350)) -> bytes:
    """Hoja A4 «escaneada» (2000×2800) con renglones y el QR chico abajo a la izquierda."""
    hoja = Image.new("L", (2000, 2800), 245)
    dibujo = ImageDraw.Draw(hoja)
    for y in range(100, 2000, 40):
        dibujo.line((100, y, 1800, y), fill=120, width=3)
    hoja.paste(imagen_qr(texto, modulo), lugar)
    if desenfoque:
        hoja = hoja.filter(ImageFilter.GaussianBlur(desenfoque * modulo))
    salida = io.BytesIO()
    hoja.convert("RGB").save(salida, "JPEG", quality=80)
    return salida.getvalue()


def test_el_servidor_lee_el_qr_nitido_borroso_y_chico_en_una_hoja_grande():
    url = url_qr(DOLARES)
    lector = LectorQRServidor()
    nitido = hoja_con_qr(url)
    assert lector.leer(nitido)[0] == url
    # Desenfoque de media celda del QR: ZXing solo ya no lo lee; con las pasadas, sí.
    borroso = hoja_con_qr(url, modulo=5, desenfoque=0.55)
    assert not zxingcpp.read_barcodes(Image.open(io.BytesIO(borroso)))
    inicio = time.monotonic()
    assert lector.leer(borroso)[0] == url
    assert time.monotonic() - inicio < 6
    # Módulos de 3 píxeles (QR de ~220 px en una hoja de 2000×2800), también borroso.
    assert lector.leer(hoja_con_qr(url, modulo=3, desenfoque=0.5))[0] == url
    # Arriba a la derecha también se encuentra.
    assert lector.leer(hoja_con_qr(url, desenfoque=0.55, lugar=(1500, 200)))[0] == url


def test_el_servidor_corta_a_tiempo_y_no_falla_con_fotos_raras():
    hoja = Image.new("RGB", (2000, 2800), "white")
    salida = io.BytesIO()
    hoja.save(salida, "JPEG")
    sin_qr = salida.getvalue()
    pasos = iter(range(1000))
    lector = LectorQRServidor(tiempo_maximo=2, reloj=lambda: next(pasos))
    assert lector.leer(sin_qr) == []
    assert next(pasos) <= 6  # cortó a las pocas pasadas
    assert LectorQRServidor().leer(b"\xff\xd8\xff no es una foto") == []
    png = io.BytesIO()
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(png, "PNG")
    assert LectorQRServidor().leer(png.getvalue()) == []


def con_lector_qr(lector=None):
    s, conector = preparado(lector or Lector())
    s.lector_qr = LectorQRServidor()
    return s, conector


def test_leer_con_qr_en_el_servidor_carga_y_controla_como_con_el_qr_del_celular():
    lector = Lector()
    s, conector = con_lector_qr(lector)
    c = cliente("ADMINISTRACION", s)
    foto = base64.b64encode(hoja_con_qr(url_qr(DOLARES), desenfoque=0.55)).decode()
    r = c.post("/controles-arca/celular/leer", json={"foto_base64": foto})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["estado"] == "listo" and not cuerpo["ya_cargada"] and cuerpo["qr"] == url_qr(DOLARES)
    assert cuerpo["factura"]["empresa"] == "ENAV" and cuerpo["factura"]["moneda"] == "DOL"
    assert cuerpo["factura"]["controlada"] and cuerpo["factura"]["tiene_foto"]
    # No hizo falta leer el texto (ni mandar la foto a ninguna IA).
    assert lector.leidas == [] and len(conector.llamadas) == 2
    # La misma factura otra vez no se duplica.
    otra = c.post("/controles-arca/celular/leer", json={"foto_base64": foto}).json()
    assert otra["ya_cargada"] and len(s.repo.facturas) == 1


def test_qr_del_servidor_con_receptor_ajeno_pide_la_empresa():
    s, conector = con_lector_qr()
    c = cliente("ADMINISTRACION", s)
    url = url_qr(datos_qr(nroDocRec=int(AJENO)))
    foto = base64.b64encode(hoja_con_qr(url)).decode()
    r = c.post("/controles-arca/celular/leer", json={"foto_base64": foto}).json()
    assert r["estado"] == "elegir_empresa" and r["qr"] == url and r["datos"]["nro_doc_receptor"] == AJENO
    assert not s.repo.facturas and not conector.llamadas
    # El celular sigue con el QR que le devolvió el servidor, como si lo hubiera leído él.
    elegida = c.post("/controles-arca/celular/qr", json={"qr": r["qr"], "foto_base64": foto, "empresa": "JUBIAR"})
    assert elegida.json()["factura"]["empresa"] == "JUBIAR"
    # O manda la empresa en la misma lectura.
    s2, _ = con_lector_qr()
    r = cliente("ADMINISTRACION", s2).post("/controles-arca/celular/leer",
                                           json={"foto_base64": foto, "empresa": "JUBIAR"}).json()
    assert r["estado"] == "listo" and r["factura"]["empresa"] == "JUBIAR"


def test_sin_qr_en_el_servidor_sigue_la_lectura_del_texto():
    lector = Lector()
    s, conector = con_lector_qr(lector)
    c = cliente("ADMINISTRACION", s)
    hoja = io.BytesIO()
    Image.new("RGB", (1200, 1600), "white").save(hoja, "JPEG")
    foto = base64.b64encode(hoja.getvalue()).decode()
    r = c.post("/controles-arca/celular/leer", json={"foto_base64": foto}).json()
    assert "estado" not in r and r["datos"]["cuit_emisor"] == PROVEEDOR and r["datos"]["codigo_autorizacion"] == CAE
    assert lector.leidas == ["image/jpeg"] and not s.repo.facturas and not conector.llamadas
    # Sólo QR (antes de pedir permiso para la IA externa): no lee el texto.
    r = c.post("/controles-arca/celular/leer", json={"foto_base64": foto, "modo": "solo_qr"}).json()
    assert "estado" not in r and set(r["datos"].values()) == {None} and lector.leidas == ["image/jpeg"]
    # Sólo texto: aunque la foto tenga QR, no lo busca.
    con_qr = base64.b64encode(hoja_con_qr(url_qr())).decode()
    r = c.post("/controles-arca/celular/leer", json={"foto_base64": con_qr, "modo": "solo_texto"}).json()
    assert "estado" not in r and len(lector.leidas) == 2 and not s.repo.facturas
    assert c.post("/controles-arca/celular/leer", json={"foto_base64": foto, "modo": "otro"}).status_code == 422


def test_un_qr_que_no_es_de_arca_en_la_foto_sigue_al_texto():
    lector = Lector()
    s, _ = con_lector_qr(lector)
    foto = base64.b64encode(hoja_con_qr("https://example.com/fe/qr/?p=eyJ2ZXIiOjF9")).decode()
    r = cliente("ADMINISTRACION", s).post("/controles-arca/celular/leer", json={"foto_base64": foto}).json()
    assert "estado" not in r and lector.leidas == ["image/jpeg"] and not s.repo.facturas


def test_si_el_lector_qr_falla_sigue_la_lectura_del_texto():
    class Roto:
        def leer(self, contenido):
            raise RuntimeError("se rompió")

    lector = Lector()
    s, _ = preparado(lector)
    s.lector_qr = Roto()
    r = cliente("ADMINISTRACION", s).post("/controles-arca/celular/leer", json={"foto_base64": FOTO}).json()
    assert "estado" not in r and lector.leidas == ["image/jpeg"]

