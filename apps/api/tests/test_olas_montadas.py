from fastapi import APIRouter

from suite_juviar.composicion.olas_3_4_5 import construir_routers
from suite_juviar.modulos.rrhh_epp.mvp import construir


def test_los_seis_modulos_exponen_routers_persistentes(monkeypatch, tmp_path):
    monkeypatch.setenv("SJ_ENTORNO", "prueba")
    rrhh = construir(entorno="prueba", ruta_base=str(tmp_path / "rrhh_epp.sqlite3"))
    routers = construir_routers(rrhh)
    assert set(routers) == {
        "epp-analitica", "legajo", "salud", "turnos", "seleccion", "capacitaciones"
    }
    assert all(isinstance(router, APIRouter) for router in routers.values())
    assert all(router.routes for router in routers.values())
