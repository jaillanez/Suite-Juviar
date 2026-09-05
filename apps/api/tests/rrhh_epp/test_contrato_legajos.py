"""Contrato que debe cumplir CUALQUIER fuente de legajos.

Hoy corre contra el YAML. El día que exista la conexión a Nexus, se agrega
LegajosNexusSQLServer a la lista de `fuentes` y estas mismas pruebas dicen si
la Vista devuelve lo que el módulo espera. Si el contrato pasa, el cambio de
fuente es una variable de entorno.
"""

import pytest

from suite_juviar.modulos.rrhh_epp.infrastructure.legajos_yaml import (
    ErrorDeDatos,
    LegajosYAML,
)

from .conftest import RUTA_LEGAJOS


@pytest.fixture(params=["yaml"])
def fuente(request):
    if request.param == "yaml":
        return LegajosYAML(RUTA_LEGAJOS)
    raise AssertionError("fuente desconocida")


def test_devuelve_las_once_columnas_de_la_vista(fuente):
    p = fuente.obtener("1042")
    assert p is not None
    assert p.legajo == "1042"
    assert p.dni == "27443110"
    assert p.puesto_codigo == "OP-BOD"
    assert p.empresa == "ENAV"
    assert p.activo is True
    assert p.nombre_completo == "Quiroga, Carlos Alberto"


def test_legajo_inexistente_devuelve_none(fuente):
    assert fuente.obtener("999999") is None


def test_legajo_dado_de_baja_se_devuelve_pero_marcado_inactivo(fuente):
    p = fuente.obtener("0988")
    assert p is not None and p.activo is False


def test_busqueda_por_apellido_dni_y_legajo(fuente):
    assert [p.legajo for p in fuente.buscar("Quiroga")] == ["1042"]
    assert [p.legajo for p in fuente.buscar("30115982")] == ["1077"]
    assert [p.legajo for p in fuente.buscar("1103")] == ["1103"]


def test_la_busqueda_no_devuelve_inactivos(fuente):
    assert fuente.buscar("Páez") == []


def test_busqueda_vacia_no_devuelve_todo(fuente):
    """Prueba de ausencia: el campo vacío no puede listar el padrón entero."""
    assert fuente.buscar("") == []
    assert fuente.buscar("   ") == []


def test_la_fuente_se_identifica(fuente):
    assert fuente.fuente in {"SIMULADA", "NEXUS"}


# --- control negativo: la carga tiene que fallar con datos mal puestos -------

def test_falla_si_falta_una_columna(tmp_path):
    archivo = tmp_path / "roto.yaml"
    archivo.write_text(
        "legajos:\n  - legajo: '1'\n    nombre: 'A'\n    apellido: 'B'\n",
        encoding="utf-8",
    )
    with pytest.raises(ErrorDeDatos) as e:
        LegajosYAML(archivo)
    assert "dni" in str(e.value)


def test_falla_si_hay_legajo_duplicado(tmp_path):
    fila = (
        "  - legajo: '1'\n    nombre: A\n    apellido: B\n    dni: '1'\n"
        "    puesto_codigo: X\n    puesto: X\n    sector_codigo: X\n    sector: X\n"
        "    empresa: ENAV\n    tipo_vinculo: PERMANENTE\n    activo: true\n"
    )
    archivo = tmp_path / "dup.yaml"
    archivo.write_text("legajos:\n" + fila + fila, encoding="utf-8")
    with pytest.raises(ErrorDeDatos):
        LegajosYAML(archivo)
