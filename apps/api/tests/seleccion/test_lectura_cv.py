"""Lectura de CV en foto o escaneados: reglas + OCR, IA automática al entrar, reproceso y datos faltantes."""

import base64
import io
import json
import struct
import tempfile
import zlib
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from suite_juviar.modulos.seleccion.api.app import construir_cvs_whatsapp, crear_app
from suite_juviar.modulos.seleccion.application.datos_cv import combinar
from suite_juviar.modulos.seleccion.application.extraccion import ExtraerDatosCV
from suite_juviar.modulos.seleccion.application.lectura_ia import LeerCVsConIA
from suite_juviar.modulos.seleccion.domain.modelos import CVOriginal, OrigenCV
from suite_juviar.modulos.seleccion.infrastructure import (
    extraccion_pdf,
    ia_deepseek,
    lectura_en_fondo,
)
from suite_juviar.modulos.seleccion.infrastructure.extraccion_pdf import (
    MAXIMO_PIXELES,
    TAMANO_MAXIMO,
    CamposPorReglasProvisorias,
    TextoPDF,
    escala_segura,
    tipo_imagen,
)
from suite_juviar.modulos.seleccion.infrastructure.extracciones_memoria import ExtraccionesEnMemoria
from suite_juviar.modulos.seleccion.infrastructure.memoria import OriginalesEnMemoria
from suite_juviar.modulos.seleccion.infrastructure.perfiles_yaml import CriteriosPerfilYAML

HOY = date(2026, 11, 26)

# Lo que dice la foto del caso real (1000022203.png), como lo devuelve el OCR.
CV_FOTO = """CURRICULUM VITAE
Juan Carlos Pérez
Edad 55 Años
Fecha Nac. 28/06/1969
Domicilio: Mendoza 1363 Capital-San Juan
Contacto: 264 6192077
juanperez69@gmail.com
Estudios cursados:
Primario: Completo
Secundario: Incompleto
Experiencia laboral
• Empresa Mapal (medio oficial gral.)
• Empresa Perfil (medio oficial gral)
• Construcciones del Oeste (ayudante de albañil)
Referencias
Disponible de inmediato
"""

FICHA_IA = {
    "nombre_completo": "Juan Carlos Pérez", "localidad": "Capital", "provincia": "San Juan",
    "edad": 55, "fecha_nacimiento": "28/06/1969", "telefono": "264 6192077",
    "email": "juanperez69@gmail.com", "nivel_estudios": "Secundario incompleto",
    "estudios": ["Primario: Completo", "Secundario: Incompleto"],
    "experiencia": [{"puesto": "Medio oficial general", "empresa": "Mapal", "periodo": None},
                    {"puesto": "Medio oficial general", "empresa": "Perfil", "periodo": None}],
    "oficios": ["medio oficial"], "resumen": "Medio oficial de construcción.",
}


def png_minimo() -> bytes:
    """PNG válido de 1×1, sólo para que la firma y Pillow lo reconozcan."""
    def bloque(tipo: bytes, datos: bytes) -> bytes:
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos))
    return (b"\x89PNG\r\n\x1a\n" + bloque(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + bloque(b"IDAT", zlib.compress(b"\x00\x00\x00\x00")) + bloque(b"IEND", b""))


def pdf(lineas: list[str]) -> bytes:
    salida = io.BytesIO()
    documento = canvas.Canvas(salida)
    for i, linea in enumerate(lineas):
        documento.drawString(40, 800 - 14 * i, linea)
    documento.save()
    return salida.getvalue()


def campos(texto: str) -> dict[str, str]:
    return {c.nombre: c.valor for c in CamposPorReglasProvisorias(lambda: HOY).extraer_campos(texto)}


# ------------------------------------------------------------------ reglas

def test_reglas_leen_el_cv_del_caso_con_titulos_y_datos_debajo():
    leidos = campos(CV_FOTO)
    assert leidos["edad_o_fecha_nacimiento"] == "57 años hoy (nació el 28/06/1969; el CV dice 55)"
    assert leidos["nivel_estudios"] == "Secundario incompleto"
    assert leidos["experiencia"].startswith("Empresa Mapal (medio oficial gral.); Empresa Perfil")
    assert leidos["oficio"] == "Medio oficial gral., Ayudante de albañil"
    assert leidos["localidad"] == "Mendoza 1363 Capital-San Juan"
    assert leidos["contacto"] == "264 6192077 · juanperez69@gmail.com"


def test_reglas_con_variantes_de_cv_argentinos():
    texto = """DATOS PERSONALES
Nombre y apellido: María Sosa
Fecha de nacimiento: 3 de marzo de 1990
Domicilio: B° Los Andes M/C 12
Rawson, San Juan
Cel. 2644-123456   e-mail: maria.sosa@hotmail.com
DNI: 35.123.456
ESTUDIOS
- Secundario completo (Escuela Técnica N° 3)
- Terciario en curso: Tecnicatura en Enología
EXPERIENCIA LABORAL
- 2018 - 2022: Bodega Las Moras, operaria de fraccionamiento
- Cosecha de uva, temporada 2023
CURSOS
Manejo de autoelevador"""
    leidos = campos(texto)
    assert leidos["edad_o_fecha_nacimiento"] == "36 años (nació el 03/03/1990)"
    assert leidos["nivel_estudios"] == "Terciario en curso"
    assert leidos["experiencia"] == ("2018 - 2022: Bodega Las Moras, operaria de fraccionamiento; "
                                     "Cosecha de uva, temporada 2023")
    assert "autoelevador" not in leidos["experiencia"]
    assert leidos["localidad"] == "B° Los Andes M/C 12, Rawson, San Juan"
    assert leidos["contacto"] == "2644-123456 · maria.sosa@hotmail.com"  # el DNI y el período no son teléfonos


def test_reglas_con_etiquetas_en_la_misma_linea_y_sin_dos_puntos():
    leidos = campos("Edad: 32 años\nEstudios: Secundario completo\nExperiencia: 4 años en bodega\n"
                    "Oficio: Operario de mantenimiento\nLocalidad: Chimbas\nTel 264 555 0101")
    assert leidos == {
        "edad_o_fecha_nacimiento": "32 años", "nivel_estudios": "Secundario completo",
        "experiencia": "4 años en bodega", "oficio": "Operario de mantenimiento",
        "localidad": "Chimbas", "contacto": "264 555 0101",
    }


def test_sin_oficio_escrito_no_se_inventa():
    leidos = campos("Experiencia laboral\n• Empresa Mapal (2019-2021)\n• Comercio familiar")
    assert "oficio" not in leidos and leidos["experiencia"] == "Empresa Mapal (2019-2021); Comercio familiar"


# ------------------------------------------------------------------ texto y OCR

def test_firmas_de_imagen_completas():
    assert tipo_imagen(b"\x89PNG\r\n\x1a\n resto") == ".png"
    assert tipo_imagen(b"\x89PNG roto") is None
    assert tipo_imagen(b"\xff\xd8\xff\xe0 jpeg") == ".jpg"
    assert tipo_imagen(b"RIFF\x10\x00\x00\x00WEBPVP8 ") == ".webp"
    assert tipo_imagen(b"RIFF\x10\x00\x00\x00AVI LIST") is None  # un RIFF que no es WEBP
    assert tipo_imagen(b"%PDF-1.4") is None


def test_foto_va_al_ocr_para_las_reglas_pero_no_tiene_capa_de_texto():
    leidas = []
    texto = TextoPDF(leer_imagen=lambda contenido, extension, segundos: leidas.append(extension) or CV_FOTO)
    foto = png_minimo()
    assert texto.extraer_texto(foto) == CV_FOTO and leidas == [".png"]
    assert texto.capa_texto(foto) == ""


def test_pdf_con_texto_no_usa_ocr_y_su_capa_es_el_texto():
    contenido = pdf(["Edad: 32 años", "Estudios: Secundario completo", "Experiencia: cosecha de uva"])
    texto = TextoPDF(leer_imagen=lambda *a: pytest.fail("no debería hacer OCR"))
    assert "Secundario completo" in texto.extraer_texto(contenido)
    assert "Secundario completo" in texto.capa_texto(contenido)


def test_pdf_escaneado_hace_ocr_con_tiempo_total_acotado():
    contenido = pdf([""] * 1)  # sin texto: como un escaneo
    reloj = iter([0.0, 0.0, 30.0, 30.0])
    llamadas = []
    texto = TextoPDF(leer_imagen=lambda c, e, segundos: llamadas.append(segundos) or "Edad 40",
                     reloj=lambda: next(reloj))
    assert "Edad 40" in texto.extraer_texto(contenido)
    assert llamadas and all(0 < s <= extraccion_pdf.TIEMPO_OCR_TOTAL for s in llamadas)
    assert texto.capa_texto(contenido) == ""
    # Pasado el tiempo total ya no se hace más OCR.
    tarde = TextoPDF(leer_imagen=lambda *a: pytest.fail("se pasó del tiempo"), reloj=iter([0.0, 25.0]).__next__)
    assert tarde.extraer_texto(contenido).strip() == ""


def test_archivo_demasiado_grande_no_se_lee():
    texto = TextoPDF(leer_imagen=lambda *a: pytest.fail("no debería leerse"))
    enorme = b"\x89PNG\r\n\x1a\n" + b"0" * (TAMANO_MAXIMO + 1)
    assert texto.extraer_texto(enorme) == "" and texto.capa_texto(enorme) == ""


def test_las_paginas_se_dibujan_con_pixeles_acotados_y_las_absurdas_se_saltean():
    assert escala_segura(595, 842, 2) == 2  # A4: tamaño normal
    escala = escala_segura(5000, 5000, 2)
    assert escala is not None and (5000 * escala) ** 2 <= MAXIMO_PIXELES * 1.001
    assert escala_segura(200_000, 200_000, 2) is None
    assert escala_segura(0, 100, 2) is None


# ------------------------------------------------------------------ IA

def cliente(entorno="prueba"):
    base = str(Path(tempfile.mkdtemp()) / "modulos.sqlite3")
    ruta = Path(__file__).parents[2] / "src/suite_juviar/modulos/seleccion/data/criterios_perfil.yaml"
    return TestClient(crear_app(CriteriosPerfilYAML(ruta), entorno, ruta_base=base),
                      headers={"X-Perfil-Simulado": "RRHH"}), base


def subir(c, nombre, contenido):
    r = c.post("/cvs/lote", json={"archivos": [
        {"nombre": nombre, "contenido_base64": base64.b64encode(contenido).decode()}]})
    assert r.status_code == 201
    return r.json()["incorporados"][0]


@pytest.fixture
def ocr_del_caso(monkeypatch):
    monkeypatch.setattr(extraccion_pdf.ocr, "leer_texto_imagen", lambda *a, **k: CV_FOTO)


def test_para_una_foto_la_ia_recibe_la_imagen_y_no_el_ocr(monkeypatch, ocr_del_caso):
    monkeypatch.setenv("SJ_IA_DEEPSEEK_API_KEY", "clave-de-prueba")
    enviados = []

    def llamar(partes, max_tokens):
        enviados.append(partes)
        return dict(FICHA_IA)

    monkeypatch.setattr(ia_deepseek, "_llamar", llamar)
    c, _ = cliente()
    cv_id = subir(c, "1000022203.png", png_minimo())
    lectura_en_fondo.esperar_todas()

    [partes] = enviados
    assert [p["type"] for p in partes] == ["text", "image_url"]
    assert partes[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "Mapal" not in partes[0]["text"]  # el texto del OCR no viaja a la IA
    assert "nivel_estudios" in partes[0]["text"] and "fecha_nacimiento" in partes[0]["text"]

    # Y a pedido («leer con IA») también manda la imagen.
    assert c.post(f"/cvs/{cv_id}/leer-ia").status_code == 200
    assert [p["type"] for p in enviados[1]] == ["text", "image_url"]


def test_para_un_pdf_con_texto_la_ia_recibe_el_texto(monkeypatch):
    enviados = []
    monkeypatch.setattr(ia_deepseek, "_llamar", lambda partes, m: enviados.append(partes) or {})
    contenido = pdf(["Juan Pérez - Edad: 40 años", "Experiencia: tractorista en finca de Caucete"])
    ia_deepseek.leer_cv("cv.pdf", contenido, TextoPDF().capa_texto(contenido))
    assert [p["type"] for p in enviados[0]] == ["text"] and "tractorista" in enviados[0][0]["text"]


def test_el_detalle_toma_los_datos_de_la_ia_y_no_hay_faltantes(monkeypatch):
    monkeypatch.setenv("SJ_IA_DEEPSEEK_API_KEY", "clave-de-prueba")
    # OCR vacío (foto ilegible para el servidor): sólo la IA leyó.
    monkeypatch.setattr(extraccion_pdf.ocr, "leer_texto_imagen", lambda *a, **k: "")
    monkeypatch.setattr(ia_deepseek, "leer_cv", lambda nombre, contenido, texto: dict(FICHA_IA))
    c, _ = cliente()
    cv_id = subir(c, "1000022203.png", png_minimo())
    lectura_en_fondo.esperar_todas()

    ficha = c.get(f"/cvs/{cv_id}").json()
    assert ficha["datos_faltantes"] == [] and ficha["lectura_ia"] == "LEIDO" and ficha["tipo"] == "imagen"
    datos = {d["nombre"]: d for d in ficha["campos"]}
    assert datos["nivel_estudios"]["valor"] == "Secundario incompleto"
    assert datos["edad_o_fecha_nacimiento"]["valor"].startswith(f"{57 if date.today() >= HOY else 56} años")
    assert datos["experiencia"]["valor"] == "Medio oficial general en Mapal; Medio oficial general en Perfil"
    assert datos["contacto"]["valor"] == "264 6192077 · juanperez69@gmail.com"
    assert datos["localidad"]["valor"] == "Capital, San Juan"
    assert all(d["origen"] == "IA" and d["verificado"] is False for d in datos.values())
    assert ficha["pendientes"] == [] and ficha["confirmaciones"] == []
    fila = c.get("/cvs").json()[0]
    assert fila["datos_faltantes"] == [] and fila["requiere_revision"] is False

    # Un dato que sólo leyó la IA se puede confirmar, y lo confirmado manda.
    r = c.put(f"/cvs/{cv_id}/campos/nivel_estudios/confirmacion", json={"valor": "Secundario incompleto"})
    assert r.status_code == 200
    datos = {d["nombre"]: d for d in c.get(f"/cvs/{cv_id}").json()["campos"]}
    assert datos["nivel_estudios"]["origen"] == "RRHH"


def test_si_la_ia_falla_las_reglas_con_ocr_completan_y_nunca_dice_que_el_cv_no_lo_trae(monkeypatch, ocr_del_caso):
    monkeypatch.setenv("SJ_IA_DEEPSEEK_API_KEY", "clave-de-prueba")

    def caida(*a):
        raise RuntimeError("La IA no respondió bien.")

    monkeypatch.setattr(ia_deepseek, "leer_cv", caida)
    monkeypatch.setattr("suite_juviar.modulos.seleccion.application.lectura_ia.ESPERAS_REINTENTO", (0, 0))
    c, _ = cliente()
    cv_id = subir(c, "foto.png", png_minimo())
    # Sin esperar a la IA: las reglas con OCR ya leyeron todo al entrar.
    ficha = c.get(f"/cvs/{cv_id}").json()
    assert ficha["datos_faltantes"] == []
    assert {d["nombre"]: d["valor"] for d in ficha["campos"]}["nivel_estudios"] == "Secundario incompleto"
    lectura_en_fondo.esperar_todas()
    ficha = c.get(f"/cvs/{cv_id}").json()
    assert ficha["lectura_ia"] == "ERROR" and "no respondió" in ficha["error_ia"]["error"]
    assert all(d["origen"] == "LECTURA_AUTOMATICA" for d in ficha["campos"])


def test_con_ocr_vacio_y_sin_ia_el_motivo_es_que_no_se_pudo_leer(monkeypatch):
    monkeypatch.setattr(extraccion_pdf.ocr, "leer_texto_imagen", lambda *a, **k: "")
    c, _ = cliente()
    cv_id = subir(c, "foto.png", png_minimo())
    ficha = c.get(f"/cvs/{cv_id}").json()
    assert ficha["motivo_faltantes"] == "NO_SE_PUDO_LEER" and ficha["texto_leido"] is False
    assert ficha["lectura_ia"] == "NO_DISPONIBLE"


def test_en_produccion_sin_autorizacion_no_se_manda_nada_a_la_ia(monkeypatch, ocr_del_caso):
    monkeypatch.setenv("SJ_IA_DEEPSEEK_API_KEY", "clave-de-prueba")
    monkeypatch.delenv("SJ_IA_EXTERNA_AUTORIZADA", raising=False)
    monkeypatch.setattr(ia_deepseek, "leer_cv", lambda *a: pytest.fail("no autorizada"))
    monkeypatch.setattr("suite_juviar.modulos.seleccion.api.app.exigir_identidad_configurada", lambda e: None)
    c, _ = cliente("produccion")
    cv_id = subir(c, "foto.png", png_minimo())
    lectura_en_fondo.esperar_todas()
    assert c.get(f"/cvs/{cv_id}").json()["lectura_ia"] == "NO_DISPONIBLE"
    assert c.post("/ia/releer").status_code == 202
    lectura_en_fondo.esperar_todas()
    assert c.get("/ia/estado").json()["leidos"] == 0


def test_reproceso_de_los_cv_ya_cargados(monkeypatch):
    # Cargados antes de este cambio: sin OCR (texto vacío) y sin IA.
    monkeypatch.setattr(extraccion_pdf.ocr, "leer_texto_imagen", lambda *a, **k: "")
    c, _base = cliente()
    viejo = subir(c, "1000022203.png", png_minimo())
    pdf_id = subir(c, "cv.pdf", pdf(["Edad: 30 años", "Estudios: Secundario completo", "Experiencia: cosecha"]))
    assert c.get(f"/cvs/{viejo}").json()["datos_faltantes"] == [
        "edad_o_fecha_nacimiento", "nivel_estudios", "experiencia"]

    # Después de instalar: OCR andando y la IA configurada.
    monkeypatch.setattr(extraccion_pdf.ocr, "leer_texto_imagen", lambda *a, **k: CV_FOTO)
    monkeypatch.setenv("SJ_IA_DEEPSEEK_API_KEY", "clave-de-prueba")
    leidos = []
    monkeypatch.setattr(ia_deepseek, "leer_cv", lambda nombre, contenido, texto: leidos.append(nombre) or dict(
        FICHA_IA))
    r = c.post("/ia/releer").json()
    assert r["encolados"] == 2
    lectura_en_fondo.esperar_todas()
    assert sorted(leidos) == ["1000022203.png", "cv.pdf"]
    estado = c.get("/ia/estado").json()
    assert (estado["leidos"], estado["en_cola"], estado["con_error"]) == (2, 0, 0)
    ficha = c.get(f"/cvs/{viejo}").json()
    assert ficha["datos_faltantes"] == [] and ficha["texto_leido"] is True
    assert {d["nombre"]: d.get("otra_lectura") for d in ficha["campos"]}["nivel_estudios"] is None
    # Leídos todos: otra pasada no vuelve a mandar nada a la IA.
    assert c.post("/ia/releer").json()["encolados"] <= 2
    lectura_en_fondo.esperar_todas()
    assert len(leidos) == 2
    assert pdf_id


def test_ver_el_detalle_no_manda_nada_a_la_ia_y_el_post_de_faltante_si(monkeypatch):
    c, _ = cliente()
    cv_id = subir(c, "cv.pdf", pdf(["Experiencia: cosecha"]))  # sin IA al entrar
    monkeypatch.setenv("SJ_IA_DEEPSEEK_API_KEY", "clave-de-prueba")
    leidos = []
    monkeypatch.setattr(ia_deepseek, "leer_cv", lambda *a: leidos.append(1) or {"nivel_estudios": "Primario completo"})
    # El GET sólo avisa que falta leerlo: no encola nada ni manda datos afuera.
    ficha = c.get(f"/cvs/{cv_id}").json()
    assert ficha["lectura_pendiente"] is True and ficha["lectura_ia"] == "SIN_LEER"
    lectura_en_fondo.esperar_todas()
    assert leidos == [] and c.get(f"/cvs/{cv_id}").json()["lectura_ia"] == "SIN_LEER"
    # El detalle lo pide con un POST, una vez.
    r = c.post(f"/cvs/{cv_id}/releer?faltante=true")
    assert r.status_code == 202 and r.json()["lectura_ia"] in {"EN_COLA", "LEYENDO", "LEIDO"}
    lectura_en_fondo.esperar_todas()
    ficha = c.get(f"/cvs/{cv_id}").json()
    assert ficha["lectura_ia"] == "LEIDO" and ficha["datos_faltantes"] == ["edad_o_fecha_nacimiento"]
    assert ficha["motivo_faltantes"] == "NO_LO_ENCONTRO" and ficha["lectura_pendiente"] is False
    # Ya leído: pedir lo faltante otra vez no vuelve a mandar nada.
    c.post(f"/cvs/{cv_id}/releer?faltante=true")
    lectura_en_fondo.esperar_todas()
    assert len(leidos) == 1


def test_cv_por_whatsapp_se_lee_con_ia_al_entrar_y_conserva_el_telefono_al_releer(monkeypatch):
    from suite_juviar.modulos.seleccion.api.app import lectura_cvs
    from suite_juviar.modulos.seleccion.infrastructure.sqlite import (
        ExtraccionesSQLite,
        fichas_ia_sqlite,
    )

    monkeypatch.setenv("SJ_IA_DEEPSEEK_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(extraccion_pdf.ocr, "leer_texto_imagen", lambda *a, **k: "")
    monkeypatch.setattr(ia_deepseek, "leer_cv", lambda *a: dict(FICHA_IA))
    base = str(Path(tempfile.mkdtemp()) / "modulos.sqlite3")
    servicio = construir_cvs_whatsapp(base, "prueba")
    assert servicio.ejecutar("5492645555555", "cv.png", png_minimo(), datetime.now(UTC), "a:1")
    lectura_en_fondo.esperar_todas()
    [cv_id] = list(fichas_ia_sqlite(base))
    assert fichas_ia_sqlite(base)[cv_id]["leido_por"] == "lectura automática"

    # Al volver a leer con OCR, el teléfono del WhatsApp (que el OCR no trae) se conserva.
    monkeypatch.setattr(extraccion_pdf.ocr, "leer_texto_imagen", lambda *a, **k: "Edad 30 años")
    _, cola = lectura_cvs(base, "prueba")
    cola.encolar(cv_id, releer_reglas=True)
    lectura_en_fondo.esperar_todas()
    campos = {c.nombre: c.valor for c in ExtraccionesSQLite(base).obtener_extraccion(cv_id).campos}
    assert campos == {"edad_o_fecha_nacimiento": "30 años", "contacto": "+5492645555555"}


# ------------------------------------------------------------------ servicio con reintentos

class TextoFijo:
    def __init__(self, texto=""):
        self.texto = texto

    def extraer_texto(self, contenido):
        return self.texto


class Reloj:
    def __init__(self):
        self.ahora = 0.0

    def __call__(self):
        return self.ahora


def servicio_lectura(leer, texto="", cvs=("cv-1",), permitida=lambda: True):
    originales, extracciones = OriginalesEnMemoria(), ExtraccionesEnMemoria()
    ahora = datetime.now(UTC)
    for cv_id in cvs:
        originales.guardar_original(CVOriginal(cv_id, OrigenCV.CORREO, f"c:{cv_id}", "cv.png", b"x", cv_id,
                                               ahora, ahora))
    fichas, errores, reloj = {}, {}, Reloj()
    lectura = LeerCVsConIA(originales, extracciones,
                           ExtraerDatosCV(originales, extracciones, TextoFijo(texto), CamposPorReglasProvisorias()),
                           fichas, errores, leer, permitida, esperas=(1, 2), reloj=reloj,
                           fallas_para_pausar=5, pausa=300)
    return lectura, fichas, errores, reloj


def reintentar(lectura, cv_id="cv-1"):
    """Lo que hace la cola: vuelve a procesar con el intento que devolvió el anterior."""
    esperas, reintento = [], lectura.procesar(cv_id)
    while reintento:
        esperas.append(reintento.segundos)
        reintento = lectura.procesar(cv_id, intento=reintento.intento)
    return esperas


def test_reintentos_acotados_sin_dormir_y_despues_queda_el_error():
    intentos = []

    def falla(cv):
        intentos.append(cv.id)
        raise RuntimeError("caída")

    lectura, fichas, errores, _ = servicio_lectura(falla)
    assert reintentar(lectura) == [1, 2]  # devuelve cuánto esperar; nunca duerme
    assert len(intentos) == 3
    assert not fichas and errores["cv-1"]["error"] == "caída" and lectura.estado("cv-1") == "ERROR"
    assert errores["cv-1"]["intentos"] == 3
    assert not lectura.necesita_ia("cv-1") and lectura.necesita_ia("cv-1", incluir_errores=True)


def test_al_segundo_intento_lee_y_borra_el_error():
    respuestas = iter([RuntimeError("caída"), {"nivel_estudios": "Secundario completo"}])

    def leer(cv):
        r = next(respuestas)
        if isinstance(r, Exception):
            raise r
        return r

    lectura, fichas, errores, _ = servicio_lectura(leer)
    errores["cv-1"] = {"error": "vieja"}
    assert reintentar(lectura) == [1]
    assert fichas["cv-1"]["nivel_estudios"] == "Secundario completo" and fichas["cv-1"]["version_lectura"] == 2
    assert errores == {}


def test_archivo_que_no_se_puede_mandar_no_se_reintenta():
    def no_es_cv(cv):
        raise ValueError("No se pudo leer este archivo: no es PDF ni imagen.")

    lectura, _, errores, _ = servicio_lectura(no_es_cv)
    assert lectura.procesar("cv-1") is None and "no es PDF ni imagen" in errores["cv-1"]["error"]


def test_con_la_ia_caida_se_pausa_sin_perder_los_pendientes():
    cvs = tuple(f"cv-{i}" for i in range(8))
    llamadas = []

    def caida(cv):
        llamadas.append(cv.id)
        raise RuntimeError("caída")

    lectura, fichas, errores, reloj = servicio_lectura(caida, cvs=cvs)
    reintentos = {cv_id: lectura.procesar(cv_id) for cv_id in cvs}
    # Cinco fallas seguidas: pausa. Los que siguen no llaman a la IA y esperan la pausa.
    assert len(llamadas) == 5 and lectura.en_pausa() == 300
    for cv_id in cvs[5:]:
        assert reintentos[cv_id].segundos == 300 and reintentos[cv_id].intento == 0
        assert errores[cv_id]["error"] == "IA no disponible, se reintenta más tarde."
        assert errores[cv_id]["en_pausa"] is True
    assert reintentos["cv-4"].segundos == 300  # el que disparó la pausa también espera
    # Pasada la pausa, la IA vuelve y los pendientes se leen.
    reloj.ahora = 301
    lectura._leer = lambda cv: {"nivel_estudios": "Primario completo"}
    for cv_id in cvs:
        assert lectura.procesar(cv_id, intento=reintentos[cv_id].intento) is None
    assert set(fichas) == set(cvs) and errores == {}


def test_la_autorizacion_se_mira_en_cada_lectura():
    autorizada = [True]
    leidos = []
    lectura, _, _, _ = servicio_lectura(lambda cv: leidos.append(cv.id) or {}, cvs=("cv-1", "cv-2"),
                                        permitida=lambda: autorizada[0])
    lectura.procesar("cv-1")
    autorizada[0] = False  # p. ej. se quitó la autorización o la clave del servidor
    lectura.procesar("cv-2")
    assert leidos == ["cv-1"] and lectura.estado("cv-2") == "NO_DISPONIBLE"


def test_la_cola_no_se_frena_con_un_reintento():
    from suite_juviar.modulos.seleccion.application.lectura_ia import Reintento

    orden = []

    def procesar(cv_id, *, releer_reglas=False, intento=0):
        orden.append((cv_id, intento))
        return Reintento(0.2, 1) if cv_id == "a" and intento == 0 else None

    cola = lectura_en_fondo.ColaLecturaCV(procesar)
    cola.encolar("a")
    cola.encolar("b")
    cola.encolar("c")
    assert not cola.esperar(0.1)  # «a» espera su reintento, los demás ya se leyeron
    assert orden == [("a", 0), ("b", 0), ("c", 0)] and cola.estado("a") == "REINTENTO"
    assert cola.progreso()["en_espera"] == 1
    assert cola.esperar(5) and orden[-1] == ("a", 1) and cola.estado("a") is None


def test_ficha_vieja_incompleta_se_vuelve_a_leer_y_la_completa_no():
    lectura, fichas, _, _ = servicio_lectura(lambda cv: {})
    fichas["cv-1"] = {"edad": 30, "estudios": [], "experiencia": []}
    assert lectura.necesita_ia("cv-1")
    fichas["cv-1"] = {"edad": 30, "estudios": ["Secundario"], "experiencia": [{"puesto": "peón"}]}
    assert not lectura.necesita_ia("cv-1")


def test_la_ia_manda_y_lo_distinto_de_las_reglas_queda_para_comparar():
    from suite_juviar.modulos.seleccion.domain.modelos import CampoExtraido, ExtraccionCV
    reglas = ExtraccionCV("cv-1", (CampoExtraido("nivel_estudios", "Secundario", "Secundario"),
                                   CampoExtraido("localidad", "Rawson", "Localidad: Rawson")), (), datetime.now(UTC))
    datos = {d["nombre"]: d for d in combinar(reglas, {"nivel_estudios": "Secundario incompleto"}, dia=HOY)}
    assert datos["nivel_estudios"]["origen"] == "IA" and datos["nivel_estudios"]["otra_lectura"] == "Secundario"
    assert datos["localidad"]["origen"] == "LECTURA_AUTOMATICA"
    assert json.dumps(datos)  # se puede mandar tal cual por la API


def test_miniatura_de_la_primera_pagina_del_pdf():
    c, _ = cliente()
    cv_id = subir(c, "cv.pdf", pdf(["Experiencia: cosecha"]))
    r = c.get(f"/cvs/{cv_id}/miniatura").json()
    assert base64.b64decode(r["contenido_base64"]).startswith(b"\x89PNG\r\n\x1a\n") and r["paginas"] == 1
    foto = subir(c, "foto.png", png_minimo())
    assert c.get(f"/cvs/{foto}/miniatura").status_code == 400
