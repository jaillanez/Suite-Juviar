from suite_juviar.modulos.rrhh_epp.mvp import RAIZ_SUITE
from suite_juviar.plataforma.parametria.infrastructure.perfiles_acceso_yaml import (
    PerfilesAccesoYAML,
)


def test_el_mapa_declara_dueno_y_estado():
    mapa = PerfilesAccesoYAML(
        RAIZ_SUITE / "plataforma" / "parametria" / "data" / "perfiles_acceso.yaml"
    )
    assert mapa.dueno_dato == "Recursos Humanos"
    assert mapa.estado == "PROVISORIO"


def test_resuelve_por_codigos_reales_y_explicitos():
    mapa = PerfilesAccesoYAML(
        RAIZ_SUITE / "plataforma" / "parametria" / "data" / "perfiles_acceso.yaml"
    )
    assert mapa.resolver("OP-PAN", "PAN") == "deposito"
    assert mapa.resolver("OP-AUT", "PAN") == "deposito"
    assert mapa.resolver("CAP-VIN", "VIN") == "campo"
    assert mapa.resolver("OP-BAS", "BAS") == "bascula"
    assert mapa.resolver("OP-CLA", "CLA") is None


def test_todo_sector_referenciado_esta_en_matriz_o_declarado_fuera(contenedor):
    mapa = contenedor.perfiles_acceso
    sectores_validos = set(contenedor.catalogo.sectores_conocidos)
    assert mapa.sectores_referenciados <= sectores_validos | mapa.sectores_fuera_matriz
    assert mapa.sectores_fuera_matriz == {"VIN"}


def test_un_sector_y_puesto_inventados_no_obtienen_perfil():
    mapa = PerfilesAccesoYAML(
        RAIZ_SUITE / "plataforma" / "parametria" / "data" / "perfiles_acceso.yaml"
    )
    assert mapa.resolver("PUESTO-INVENTADO", "SECTOR-INVENTADO") is None
