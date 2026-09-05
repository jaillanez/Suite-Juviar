import pytest

from suite_juviar.modulos.rrhh_epp.mvp import RAIZ, construir

RUTA_LEGAJOS = RAIZ / "data" / "nexus_simulado.yaml"


@pytest.fixture
def contenedor():
    """Contenedor de prueba, con la base en memoria: no ensucia el disco."""
    return construir(entorno="prueba", fuente_legajos="yaml", ruta_base=":memory:")


@pytest.fixture
def cliente(contenedor):
    from fastapi.testclient import TestClient

    from suite_juviar.modulos.rrhh_epp.api.mvp import crear_app

    return TestClient(
        crear_app(contenedor), headers={"X-Legajo-Usuario": "1210"}
    )
