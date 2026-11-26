"""Controles de la lectura de CV: topes de tamaño, tipo por contenido y autorización de la IA."""

import base64
import inspect
import io
import struct
import tempfile
import zlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from suite_juviar.modulos.seleccion.api import app as api
from suite_juviar.modulos.seleccion.domain.modelos import CVOriginal, OrigenCV
from suite_juviar.modulos.seleccion.infrastructure import extraccion_pdf, ia_deepseek
from suite_juviar.modulos.seleccion.infrastructure.extraccion_pdf import TAMANO_MAXIMO, TextoPDF
from suite_juviar.modulos.seleccion.infrastructure.sqlite import OriginalesSQLite

from .test_lectura_cv import cliente, pdf, png_minimo, subir


def png_de(ancho, alto):
    from PIL import Image
    salida = io.BytesIO()
    Image.new("RGB", (ancho, alto), "white").save(salida, format="PNG")
    return salida.getvalue()


def png_con_encabezado(ancho, alto):
    """Sólo el encabezado dice el tamaño: no hace falta armar la imagen entera."""
    def bloque(tipo, datos):
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos))
    return (b"\x89PNG\r\n\x1a\n" + bloque(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
            + bloque(b"IDAT", zlib.compress(b"\x00")) + bloque(b"IEND", b""))


def guardar(base, cv_id, nombre, contenido):
    ahora = datetime.now(UTC)
    OriginalesSQLite(base).guardar_original(
        CVOriginal(cv_id, OrigenCV.CORREO, f"c:{cv_id}", nombre, contenido, cv_id, ahora, ahora))


@pytest.fixture
def topes_chicos(monkeypatch):
    from PIL import Image
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", Image.MAX_IMAGE_PIXELS)  # se restaura al final
    monkeypatch.setattr(extraccion_pdf, "MAXIMO_PIXELES", 100)
    monkeypatch.setattr(extraccion_pdf, "MAXIMO_PIXELES_IMAGEN", 400)


# ------------------------------------------------------------------ 1. fotos al OCR

def test_foto_ilegible_o_gigante_no_va_al_ocr(topes_chicos):
    texto = TextoPDF(leer_imagen=lambda *a: pytest.fail("no debería hacer OCR"))
    assert texto.extraer_texto(b"\x89PNG\r\n\x1a\n" + b"basura" * 50) == ""  # firma de PNG, contenido roto
    assert texto.extraer_texto(png_de(30, 30)) == ""  # 900 píxeles: pasa del tope
    assert texto.extraer_texto(png_con_encabezado(60_000, 60_000)) == ""  # bomba de descompresión


@pytest.mark.filterwarnings("ignore::PIL.Image.DecompressionBombWarning")  # Pillow avisa; nosotros cortamos
def test_foto_gigante_con_los_topes_reales_no_va_al_ocr():
    texto = TextoPDF(leer_imagen=lambda *a: pytest.fail("no debería hacer OCR"))
    lado = int((extraccion_pdf.MAXIMO_PIXELES_IMAGEN + 1) ** 0.5) + 1
    assert texto.extraer_texto(png_con_encabezado(lado, lado)) == ""


def test_foto_grande_dentro_del_tope_se_achica_antes_del_ocr(topes_chicos):
    from PIL import Image
    recibidas = []
    texto = TextoPDF(leer_imagen=lambda contenido, extension, s: recibidas.append((contenido, extension)) or "ok")
    assert texto.extraer_texto(png_de(15, 15)) == "ok"  # 225 píxeles: entre el de trabajo y el tope
    [(contenido, extension)] = recibidas
    with Image.open(io.BytesIO(contenido)) as imagen:
        assert imagen.size[0] * imagen.size[1] <= 100 and extension == ".png"


# ------------------------------------------------------------------ 2. topes de bytes

def test_el_tamano_maximo_vale_para_contar_y_dibujar_paginas():
    contenido = pdf(["Hola"])
    assert extraccion_pdf.cantidad_paginas(contenido) == 1
    assert extraccion_pdf.cantidad_paginas(b"no es pdf") is None
    enorme = contenido + b"%" * (TAMANO_MAXIMO + 1)
    assert extraccion_pdf.cantidad_paginas(enorme) is None and extraccion_pdf.paginas_png(enorme, 1, 1) == []


def test_la_carga_manual_rechaza_archivos_mas_grandes_que_el_tope():
    c, _ = cliente()
    chico = base64.b64encode(pdf(["Hola"])).decode()
    grande = base64.b64encode(b"%PDF" + b"0" * TAMANO_MAXIMO).decode()
    r = c.post("/cvs/lote", json={"archivos": [{"nombre": "ok.pdf", "contenido_base64": chico},
                                               {"nombre": "enorme.pdf", "contenido_base64": grande}]})
    assert r.status_code == 413 and "enorme.pdf" in r.json()["detail"]
    assert c.get("/cvs").json() == []  # todo o nada: no entró ni el chico
    assert c.post("/cvs/lote", json={"archivos": [{"nombre": "x", "contenido_base64": "no*base64"}]}
                  ).status_code == 400


def test_la_miniatura_respeta_el_tamano_maximo():
    c, base = cliente()
    guardar(base, "enorme", "cv.pdf", pdf(["Hola"]) + b"%" * TAMANO_MAXIMO)
    assert c.get("/cvs/enorme/miniatura").status_code == 413
    cv_id = subir(c, "cv.pdf", pdf(["Hola"]))
    r = c.get(f"/cvs/{cv_id}/miniatura")
    assert r.status_code == 200 and r.json()["paginas"] == 1


# ------------------------------------------------------------------ 4. tipo por contenido

def test_la_ia_decide_el_tipo_solo_por_el_contenido(monkeypatch):
    enviados = []
    monkeypatch.setattr(ia_deepseek, "_llamar", lambda partes, m: enviados.append(partes) or {})
    # Una foto con nombre de texto va como imagen.
    ia_deepseek.leer_cv("cv.txt", png_minimo(), "")
    assert enviados[-1][1]["image_url"]["url"].startswith("data:image/png;base64,")
    # Un archivo que no es PDF ni imagen no se manda, aunque se llame .png o traiga texto.
    for nombre, texto in (("cv.png", ""), ("cv.pdf", "texto suficiente para parecer un currículum")):
        with pytest.raises(ValueError, match="no es PDF ni imagen"):
            ia_deepseek.leer_cv(nombre, b"<html>no es un cv</html>", texto)
    assert len(enviados) == 1


def test_leer_con_ia_un_archivo_que_no_es_pdf_ni_imagen_da_422(monkeypatch):
    monkeypatch.setenv("SJ_IA_DEEPSEEK_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(ia_deepseek, "_llamar", lambda *a: pytest.fail("no se manda"))
    c, base = cliente()
    guardar(base, "raro", "cv.png", b"MZ\x90 ejecutable")
    r = c.post("/cvs/raro/leer-ia")
    assert r.status_code == 422 and "no es PDF ni imagen" in r.json()["detail"]


# ------------------------------------------------------------------ 6. autorización en el momento

def test_sin_entorno_no_hay_ia_y_manda_el_mas_restrictivo(monkeypatch):
    monkeypatch.setenv("SJ_IA_DEEPSEEK_API_KEY", "clave-de-prueba")
    monkeypatch.delenv("SJ_IA_EXTERNA_AUTORIZADA", raising=False)
    for funcion in (api.crear_router, api.crear_app, api.lectura_cvs):
        assert inspect.signature(funcion).parameters["entorno"].default is inspect.Parameter.empty
    base = str(Path(tempfile.mkdtemp()) / "modulos.sqlite3")
    assert not api.ia_autorizada(base)  # nadie dijo el entorno: como producción
    lectura, _ = api.lectura_cvs(base, "prueba")
    assert lectura.permitida()  # el servidor de prueba sigue con la IA
    api.lectura_cvs(base, "produccion")  # otro camino de la misma base, en producción
    assert not lectura.permitida()  # la cola ya creada lo ve en la lectura siguiente
    monkeypatch.setenv("SJ_IA_EXTERNA_AUTORIZADA", "1")
    assert lectura.permitida()
