import base64
from datetime import UTC, datetime, timedelta

import pytest

from suite_juviar.modulos.seleccion.application.datos_faltantes import datos_faltantes
from suite_juviar.modulos.seleccion.application.genero import genero_de, genero_por_nombre
from suite_juviar.modulos.seleccion.infrastructure import ia_deepseek

from .test_api_gestion import cliente, pdf


@pytest.mark.parametrize("nombre,esperado", [
    ("María José Pérez", "F"), ("José María Pérez", "M"), ("Luca Gómez", "M"), ("Rocío Díaz", "F"),
    ("Bautista Ruiz", "M"), ("Isabel Ríos", "F"), ("Nahiara Sosa", "F"), ("Tadeo López", "M"),
    ("JUAN CARLOS ROJAS", "M"), ("Andrea Funes", "F"), ("Ezequiel Ibáñez", "M"), ("Abigail Rey", "F"),
])
def test_genero_por_nombre_de_pila(nombre, esperado):
    assert genero_por_nombre(nombre) == esperado


def test_lo_que_dice_el_cv_manda_sobre_el_nombre_y_si_no_hay_nada_queda_vacio():
    assert genero_de({"nombre_completo": "Andrea Funes", "genero": "Masculino"}) == {"genero": "M", "origen": "CV"}
    assert genero_de({"nombre_completo": "Andrea Funes"}) == {"genero": "F", "origen": "NOMBRE"}
    assert genero_de({"nombre_completo": "Kim Lee"}) == {"genero": None, "origen": None}
    assert genero_de(None) == {"genero": None, "origen": None}


def test_faltantes_cuenta_lo_que_leyo_la_ia():
    assert datos_faltantes([]) == ["edad_o_fecha_nacimiento", "nivel_estudios", "experiencia"]
    assert datos_faltantes(["experiencia"], {"edad": 30, "estudios": []}) == ["nivel_estudios"]
    assert datos_faltantes([], {"edad": "34", "estudios": ["Secundario"], "experiencia": [{"puesto": "x"}]}) == []


def subir(c, nombre, texto):
    contenido = base64.b64encode(pdf(texto)).decode()
    return c.post("/cvs/lote", json={"archivos": [{"nombre": nombre, "contenido_base64": contenido}]}).json()


def test_lista_y_ficha_muestran_faltantes_genero_y_fecha_de_carga(monkeypatch):
    monkeypatch.setenv("SJ_IA_DEEPSEEK_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(ia_deepseek, "leer_cv", lambda nombre, contenido, texto: {
        "nombre_completo": "Rocío Díaz", "edad": 31, "estudios": [], "experiencia": []})
    c = cliente()
    cv_id = subir(c, "cv.pdf", "Experiencia: cosecha")["incorporados"][0]

    fila = c.get("/cvs").json()[0]
    assert fila["datos_faltantes"] == ["edad_o_fecha_nacimiento", "nivel_estudios"]
    assert fila["genero"] is None and fila["cargado_en"]

    c.post(f"/cvs/{cv_id}/leer-ia")
    ficha = c.get(f"/cvs/{cv_id}").json()
    assert ficha["datos_faltantes"] == ["nivel_estudios"]
    assert (ficha["genero"], ficha["origen"]) == ("F", "NOMBRE")


def test_filtro_por_fecha_de_carga(monkeypatch):
    c = cliente()
    subir(c, "cv.pdf", "Experiencia: cosecha")
    hoy = datetime.now(UTC).astimezone(__import__("zoneinfo").ZoneInfo("America/Argentina/San_Juan")).date()
    ayer, manana = hoy - timedelta(days=1), hoy + timedelta(days=1)

    assert len(c.get(f"/cvs?desde={hoy}&hasta={hoy}").json()) == 1
    assert c.get(f"/cvs?hasta={ayer}").json() == []
    assert c.get(f"/cvs?desde={manana}").json() == []
    assert len(c.get(f"/revision?desde={hoy}").json()) == 1
    assert c.get(f"/revision?desde={manana}").json() == []
    assert c.get(f"/cvs?desde={manana}&hasta={hoy}").status_code == 400


def test_la_busqueda_con_ia_respeta_el_periodo_y_recibe_el_genero(monkeypatch):
    monkeypatch.setenv("SJ_IA_DEEPSEEK_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(ia_deepseek, "leer_cv", lambda nombre, contenido, texto: {"nombre_completo": "Lucas Paz"})
    recibidas = {}

    def buscar(pedido, fichas):
        recibidas.update(fichas)
        return [{"id": i, "encaje": "ALTO", "motivos": [], "faltan": []} for i in fichas]

    monkeypatch.setattr(ia_deepseek, "buscar_candidatos", buscar)
    c = cliente()
    cv_id = subir(c, "cv.pdf", "Experiencia: cosecha")["incorporados"][0]
    c.post(f"/cvs/{cv_id}/leer-ia")
    hoy = datetime.now(UTC).astimezone(__import__("zoneinfo").ZoneInfo("America/Argentina/San_Juan")).date()

    afuera = c.post("/ia/buscar", json={"pedido": "capataz con experiencia", "desde": str(hoy + timedelta(days=1))})
    assert afuera.json()["candidatos"] == [] and not recibidas

    adentro = c.post("/ia/buscar", json={"pedido": "capataz con experiencia", "desde": str(hoy)})
    assert [x["id"] for x in adentro.json()["candidatos"]] == [cv_id]
    assert recibidas[cv_id]["genero"] == "masculino (deducido del nombre)"


@pytest.mark.parametrize("declarado,esperado", [
    ("Sexo: F", "F"), ("Género: femenino", "F"), ("masculino", "M"), ("No binario", "X"),
    ("prefiero no decirlo", None), ("F / M", None), ("otra persona", None), ("M en ciencias", None),
    ("Sexo F", "F"),
])
def test_lo_declarado_en_el_cv_nunca_se_reemplaza_por_el_nombre(declarado, esperado):
    assert genero_de({"nombre_completo": "Andrea Funes", "genero": declarado}) == {"genero": esperado, "origen": "CV"}


def test_un_apellido_no_decide_el_genero():
    assert genero_por_nombre("Kim García") is None
