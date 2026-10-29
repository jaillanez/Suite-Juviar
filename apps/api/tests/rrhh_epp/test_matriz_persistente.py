from suite_juviar.modulos.rrhh_epp.domain.modelos_mvp import RequisitoEPP
from suite_juviar.modulos.rrhh_epp.infrastructure.catalogo_yaml import CatalogoYAML
from suite_juviar.modulos.rrhh_epp.mvp import RAIZ


def catalogo(ruta):
    d = RAIZ / "data"
    return CatalogoYAML(d / "catalogo_rd068.yaml", d / "matriz_sector_puesto_epp.yaml",
                        d / "vida_util_referencial.yaml", d / "catalogo_items.yaml", ruta)


def test_los_cambios_de_la_matriz_sobreviven_a_un_reinicio(tmp_path):
    ruta = tmp_path / "matriz_cambios.json"
    primero = catalogo(ruta)
    codigo = next(iter(primero._elementos))
    requisito = RequisitoEPP(codigo, 2, "ANUAL", "TODO_EL_ANIO", True, "riesgo de prueba", "PUESTO")
    primero.guardar_matriz_puesto("OP-BOD", [requisito], "rrhh@enav.com")
    segundo = catalogo(ruta)
    assert segundo.matriz_puesto("OP-BOD") == [requisito]
    assert segundo.historial_matriz[-1]["autor"] == "rrhh@enav.com"
    assert catalogo(None).matriz_puesto("OP-BOD") != [requisito]
