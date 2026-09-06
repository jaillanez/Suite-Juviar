"""La matriz decide qué protección recibe una persona."""

import pytest

from suite_juviar.modulos.rrhh_epp.infrastructure.catalogo_yaml import (
    CatalogoYAML,
    ErrorDeCatalogo,
)
from suite_juviar.modulos.rrhh_epp.mvp import RAIZ


def test_estan_los_19_sectores_del_esquema_de_enav(contenedor):
    esperados = {
        "BOD", "COL", "CLA", "FIL", "CON", "EFL", "FVA", "ENV", "LIM", "MEC",
        "ELE", "CAL", "LAB", "ADM", "BAS", "MAE", "PAN", "LAG", "PRE",
    }
    assert set(contenedor.catalogo.sectores_conocidos) == esperados


def test_suma_base_mas_sector(contenedor):
    requisitos = contenedor.catalogo.requisitos_de("CLA", "OP-CLA")
    origenes = {requisito.codigo: requisito.origen for requisito in requisitos}
    assert origenes["8"] == "BASE"
    assert origenes["10"] == "SECTOR"


def test_el_puesto_se_suma_y_pisa_niveles_menos_especificos(contenedor):
    requisitos = {
        requisito.codigo: requisito
        for requisito in contenedor.catalogo.requisitos_de("PAN", "OP-AUT")
    }
    assert requisitos["62"].origen == "PUESTO"
    assert requisitos["142"].origen == "PUESTO"


def test_un_sector_sin_matriz_igual_recibe_la_base(contenedor):
    assert contenedor.catalogo.sector_definido("VIN") is False
    requisitos = contenedor.catalogo.requisitos_de("VIN", "COSECHERO")
    assert any(requisito.origen == "BASE" for requisito in requisitos)
    assert any(requisito.origen == "PUESTO" for requisito in requisitos)


def test_administracion_no_recibe_la_base_operativa(contenedor):
    assert contenedor.catalogo.requisitos_de("ADM", "ADMINISTRATIVO") == []


def test_toda_linea_declara_fundamento(contenedor):
    for sector in contenedor.catalogo.sectores_conocidos:
        for requisito in contenedor.catalogo.requisitos_de(sector, ""):
            assert requisito.fundamento, f"{sector}/{requisito.codigo} sin fundamento"


def test_la_matriz_esta_marcada_como_no_validada(contenedor):
    assert contenedor.catalogo.estado_matriz == "PROPUESTA_SIN_VALIDAR"


def test_a_igual_nivel_gana_la_cantidad_mayor(tmp_path):
    matriz = tmp_path / "matriz.yaml"
    matriz.write_text(
        "estado: PRUEBA\nsectores:\n  XX:\n    nombre: X\n    elementos:\n"
        "      - {codigo: '5', cantidad: 1}\n"
        "      - {codigo: '5', cantidad: 3}\n",
        encoding="utf-8",
    )
    catalogo = CatalogoYAML(RAIZ / "data" / "catalogo_rd068.yaml", matriz)
    requisitos = catalogo.requisitos_de("XX", "")
    assert len(requisitos) == 1
    assert requisitos[0].cantidad == 3


def test_no_arranca_si_la_matriz_apunta_a_un_codigo_inexistente(tmp_path):
    matriz = tmp_path / "matriz.yaml"
    matriz.write_text(
        "estado: PRUEBA\nsectores:\n  XX:\n    nombre: X\n    elementos:\n"
        "      - {codigo: '99999', cantidad: 1}\n",
        encoding="utf-8",
    )
    with pytest.raises(ErrorDeCatalogo, match="99999"):
        CatalogoYAML(RAIZ / "data" / "catalogo_rd068.yaml", matriz)


def test_no_arranca_con_una_frecuencia_invalida(tmp_path):
    matriz = tmp_path / "matriz.yaml"
    matriz.write_text(
        "estado: PRUEBA\nsectores:\n  XX:\n    nombre: X\n    elementos:\n"
        "      - {codigo: '5', cantidad: 1, frecuencia: CUANDO_SE_ACUERDEN}\n",
        encoding="utf-8",
    )
    with pytest.raises(ErrorDeCatalogo):
        CatalogoYAML(RAIZ / "data" / "catalogo_rd068.yaml", matriz)


def test_la_faja_lumbar_no_figura_en_ninguna_combinacion(contenedor):
    assert contenedor.catalogo.obtener_elemento("33") is not None
    puestos = ("", "OP-AUT", "SOLDADOR", "COSECHERO", "BOSQUE")
    for sector in contenedor.catalogo.sectores_conocidos:
        for puesto in puestos:
            codigos = {
                requisito.codigo
                for requisito in contenedor.catalogo.requisitos_de(sector, puesto)
            }
            assert "33" not in codigos, f"la faja aparece en {sector}/{puesto}"


def test_el_dielectrico_nunca_sale_sin_sobreguante(contenedor):
    for sector in contenedor.catalogo.sectores_conocidos:
        codigos = {
            requisito.codigo
            for requisito in contenedor.catalogo.requisitos_de(sector, "")
        }
        if "71" in codigos or "134" in codigos:
            assert "72" in codigos, f"{sector} entrega dieléctrico sin sobreguante"
