import pytest

from suite_juviar.modulos.rrhh_epp.infrastructure.catalogo_yaml import CatalogoYAML, _orden_codigo
from suite_juviar.modulos.rrhh_epp.mvp import RAIZ


@pytest.fixture
def catalogo_real(tmp_path):
    matriz_vacia = tmp_path / "matriz.yaml"
    matriz_vacia.write_text("estado: TRANSICION_CATALOGO_REAL\npuestos: {}\n", encoding="utf-8")
    return CatalogoYAML(RAIZ / "data" / "catalogo_rd068.yaml", matriz_vacia)


def test_el_catalogo_tiene_los_145_elementos_reales(catalogo_real):
    elementos = catalogo_real.listar_elementos()
    assert len(elementos) == 145
    assert "V 02" in catalogo_real.version_norma


def test_el_codigo_con_sufijo_se_conserva_como_texto(catalogo_real):
    elemento = catalogo_real.obtener_elemento("104-B")
    assert elemento is not None
    assert elemento.codigo == "104-B"


def test_los_codigos_se_ordenan_numericamente_aunque_sean_texto(catalogo_real):
    codigos = [elemento.codigo for elemento in catalogo_real.listar_elementos()]
    assert codigos.index("9") < codigos.index("114")
    assert _orden_codigo("104") < _orden_codigo("104-B") < _orden_codigo("114")
