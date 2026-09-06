"""Lo que el sistema tiene que RECHAZAR pesa más que lo que acepta."""

import pytest

from suite_juviar.modulos.rrhh_epp.domain.modelos_mvp import (
    CantidadInvalida,
    CodigoFueraDeCatalogo,
    EntregaSinLineas,
    FirmaFaltante,
    ItemFueraDeCatalogo,
    LegajoInactivo,
    LegajoInexistente,
    MetodoDeFirmaNoHabilitado,
)
from suite_juviar.modulos.rrhh_epp.mvp import ErrorDeConfiguracion, construir


def entregar(contenedor, **cambios):
    argumentos = {
        "numero_legajo": "1042",
        "items": [{"codigo": "68", "item_codigo": "SIM-68-01", "cantidad": 2}],
        "metodo_firma": "TRAZO_TABLET",
        "evidencia_firma": "data:image/png;base64,AAAA",
        "usuario_deposito": "deposito",
    }
    argumentos.update(cambios)
    return contenedor.registrar_entrega.ejecutar(**argumentos)


# --- camino feliz -----------------------------------------------------------

def test_registra_y_copia_los_datos_del_catalogo(contenedor):
    e = entregar(contenedor)
    assert e.legajo.dni == "27443110"          # vino de la fuente, no se tipeó
    assert e.lineas[0].producto == "Guantes"
    assert e.lineas[0].tipo_modelo == "Guantes de Nitrilo Azul (Corto Cod.13255)"
    assert e.lineas[0].marca == "DPS"
    assert e.lineas[0].posee_certificacion is True
    assert e.lineas[0].item_codigo == "SIM-68-01"
    assert e.lineas[0].estado_item == "SIMULADO"
    assert e.cantidad_items == 2


def test_la_firma_de_prueba_queda_marcada_como_simulada(contenedor):
    e = entregar(contenedor)
    assert e.firma_trabajador.simulada is True
    assert e.firma_empresa is None


def test_el_pin_no_se_guarda_en_claro(contenedor):
    e = entregar(contenedor, metodo_firma="PIN", evidencia_firma="4815")
    assert "4815" not in e.firma_trabajador.evidencia
    assert e.firma_trabajador.evidencia.startswith("sha256:")


def test_deja_bitacora(contenedor):
    e = entregar(contenedor)
    ultimo = contenedor.bitacora.ultimos(1)[0]
    assert ultimo["evento"] == "ENTREGA_EPP_REGISTRADA"
    assert ultimo["detalle"]["id_entrega"] == e.id
    assert ultimo["detalle"]["fuente_legajos"] == "SIMULADA"


def test_la_entrega_se_recupera_igual_a_como_se_guardo(contenedor):
    e = entregar(contenedor)
    guardada = contenedor.entregas.obtener(e.id)
    assert guardada == e


# --- rechazos ---------------------------------------------------------------

def test_rechaza_legajo_inexistente(contenedor):
    with pytest.raises(LegajoInexistente):
        entregar(contenedor, numero_legajo="999999")


def test_rechaza_legajo_dado_de_baja(contenedor):
    with pytest.raises(LegajoInactivo):
        entregar(contenedor, numero_legajo="0988")


def test_rechaza_codigo_fuera_del_catalogo(contenedor):
    """Regla 3: nada de texto libre donde hay catálogo."""
    with pytest.raises(CodigoFueraDeCatalogo):
        entregar(contenedor, items=[{"codigo": "9999", "cantidad": 1}])


def test_rechaza_codigo_vacio(contenedor):
    with pytest.raises(CodigoFueraDeCatalogo):
        entregar(contenedor, items=[{"codigo": "", "cantidad": 1}])


@pytest.mark.parametrize("item_codigo", ["", None, "SIM-69-01", "NO-EXISTE"])
def test_rechaza_item_vacio_nulo_ajeno_o_inexistente(contenedor, item_codigo):
    with pytest.raises(ItemFueraDeCatalogo):
        entregar(contenedor, items=[{
            "codigo": "68",
            "item_codigo": item_codigo,
            "cantidad": 1,
        }])


def test_rechaza_entrega_sin_elementos(contenedor):
    with pytest.raises(EntregaSinLineas):
        entregar(contenedor, items=[])


@pytest.mark.parametrize("cantidad", [0, -1, 1.5, "2", None, True])
def test_rechaza_cantidades_invalidas(contenedor, cantidad):
    with pytest.raises(CantidadInvalida):
        entregar(contenedor, items=[{
            "codigo": "68",
            "item_codigo": "SIM-68-01",
            "cantidad": cantidad,
        }])


@pytest.mark.parametrize("evidencia", ["", "   ", None])
def test_rechaza_entrega_sin_firma(contenedor, evidencia):
    """Prueba de ausencia: sin conformidad no hay constancia."""
    with pytest.raises(FirmaFaltante):
        entregar(contenedor, evidencia_firma=evidencia)


def test_rechaza_metodo_de_firma_no_habilitado(contenedor):
    with pytest.raises(MetodoDeFirmaNoHabilitado):
        entregar(contenedor, metodo_firma="BIOMETRIA")


def test_nada_se_guarda_cuando_la_entrega_se_rechaza(contenedor):
    with pytest.raises(CodigoFueraDeCatalogo):
        entregar(contenedor, items=[{"codigo": "9999", "cantidad": 1}])
    assert contenedor.entregas.listar_por_legajo("1042") == []


# --- guardas de configuración ----------------------------------------------

def test_produccion_con_fuente_simulada_no_arranca(monkeypatch):
    """La fuente de prueba no puede llegar a producción por descuido."""
    with pytest.raises(ErrorDeConfiguracion):
        construir(entorno="produccion", fuente_legajos="yaml", ruta_base=":memory:")


def test_produccion_con_nexus_sin_cadena_de_conexion_no_arranca(monkeypatch):
    monkeypatch.delenv("NEXUS_CONEXION", raising=False)
    with pytest.raises(ErrorDeConfiguracion):
        construir(entorno="produccion", fuente_legajos="nexus", ruta_base=":memory:")


def test_fuente_desconocida_no_arranca():
    with pytest.raises(ErrorDeConfiguracion):
        construir(entorno="prueba", fuente_legajos="mongodb", ruta_base=":memory:")


def test_identidad_declarada_debe_habilitarse_expresamente(monkeypatch):
    monkeypatch.delenv("SJ_HABILITAR_IDENTIDAD_DECLARADA", raising=False)
    with pytest.raises(ErrorDeConfiguracion, match="SJ_HABILITAR_IDENTIDAD_DECLARADA"):
        construir(entorno="desarrollo", fuente_legajos="yaml", ruta_base=":memory:")


def test_control_negativo_de_la_guarda(monkeypatch):
    """Si la guarda estuviera mal escrita, esto pasaría igual y no mediría nada.

    Confirma que la combinación permitida SÍ construye: así sabemos que las
    tres pruebas de arriba fallan por la guarda y no porque construir() falle
    siempre.
    """
    monkeypatch.setenv("SJ_HABILITAR_IDENTIDAD_DECLARADA", "SI")
    c = construir(entorno="desarrollo", fuente_legajos="yaml", ruta_base=":memory:")
    assert c.modo_simulado is True
