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


def test_resuelve_por_codigos_estables_no_por_descripcion():
    mapa = PerfilesAccesoYAML(
        RAIZ_SUITE / "plataforma" / "parametria" / "data" / "perfiles_acceso.yaml"
    )
    assert mapa.resolver("OP-DEP", "OTRO") == "deposito"
    assert mapa.resolver("OTRO", "DEP") == "deposito"
    assert mapa.resolver("CAP-VIN", "VIN") == "campo"
    assert mapa.resolver("OP-BAS", "BAS") == "bascula"
    assert mapa.resolver("OP-CLA", "CLA") is None
