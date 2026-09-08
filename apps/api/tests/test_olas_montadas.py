from suite_juviar.composicion.olas_3_4_5 import construir_subaplicaciones
from suite_juviar.modulos.rrhh_epp.mvp import construir


def test_las_seis_aplicaciones_quedan_montables_y_navegables(monkeypatch):
    monkeypatch.setenv("SJ_ENTORNO", "prueba")
    rrhh = construir(entorno="prueba", ruta_base=":memory:")
    aplicaciones = construir_subaplicaciones(rrhh)
    assert set(aplicaciones) == {
        "epp-analitica", "legajo", "salud", "turnos", "seleccion", "capacitaciones"
    }
    assert {app.title for app in aplicaciones.values()} == {
        "Analítica EPP para Compras",
        "Legajo digital",
        "Salud laboral",
        "Conciliación de turnos",
        "Selección de personal",
        "Capacitaciones",
    }
