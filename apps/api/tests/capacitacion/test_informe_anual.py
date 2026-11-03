import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from suite_juviar.modulos.capacitacion.api.app import crear_app
from suite_juviar.modulos.capacitacion.infrastructure.configuracion_yaml import (
    ConfiguracionCapacitacionYAML,
)


@dataclass(frozen=True)
class Persona:
    legajo: str
    nombre_completo: str
    empresa: str
    sector: str
    puesto: str


class Padron:
    simulada = True

    def __init__(self, personas):
        self._personas = {p.legajo: p for p in personas}

    def obtener(self, legajo):
        return self._personas.get(legajo)

    def buscar(self, *, sector=None, empresa=None):
        return [p for p in self._personas.values()
                if (not sector or sector.casefold() in p.sector.casefold())
                and (not empresa or empresa.casefold() in p.empresa.casefold())]


PADRON = Padron([
    Persona("100", "Pérez Ana", "ENAV", "Bodega", "Operaria"),
    Persona("200", "Gómez Luis", "ENAV", "Bodega", "Operario"),
    Persona("300", "Díaz Carla", "JUBIAR", "Administración", "Auxiliar"),
])


def cliente(padron=PADRON) -> TestClient:
    ruta = Path(__file__).parents[2] / "src/suite_juviar/modulos/capacitacion/data/configuracion.yaml"
    base = str(Path(tempfile.mkdtemp()) / "modulos.sqlite3")
    app = crear_app(ConfiguracionCapacitacionYAML(ruta), ruta_base=base, padron=padron)
    return TestClient(app, headers={"X-Perfil-Simulado": "RRHH"})


def _dictado(c, tema_id, fecha):
    return c.post("/dictados", json={"tema_id": tema_id, "fecha": fecha, "instructor": "HyS"}).json()["id"]


def _presente(c, dictado_id, legajo, nombre):
    r = c.post(f"/dictados/{dictado_id}/asistencias",
               json={"legajo": legajo, "nombre_completo": nombre, "presente": True})
    assert r.status_code == 201


def test_informe_lista_historial_y_quienes_no_se_capacitaron():
    c = cliente()
    altura = c.post("/temas", json={"nombre": "Trabajo en altura", "horas": 2}).json()["id"]
    fuego = c.post("/temas", json={"nombre": "Uso de matafuegos", "horas": 1.5}).json()["id"]
    d1 = _dictado(c, altura, "2026-03-10")
    d2 = _dictado(c, altura, "2026-09-01")
    d3 = _dictado(c, fuego, "2026-05-05")
    viejo = _dictado(c, fuego, "2025-12-20")
    _presente(c, d1, "100", "Perez Ana")
    _presente(c, d2, "100", "Perez Ana")  # repite el tema: suma horas una sola vez
    _presente(c, d3, "100", "Perez Ana")
    _presente(c, viejo, "200", "Gómez Luis")  # del año anterior: no cuenta
    _presente(c, d3, "999", "Ex Empleado")  # ya no está en el padrón

    informe = c.get("/informe-anual?anio=2026").json()

    assert informe["en_padron"] == 3
    assert informe["padron_simulado"] is True
    por_legajo = {t["legajo"]: t for t in informe["trabajadores"]}
    assert set(por_legajo) == {"100", "999"}
    ana = por_legajo["100"]
    assert ana["nombre_completo"] == "Pérez Ana" and ana["empresa"] == "ENAV" and ana["en_padron"]
    assert ana["horas"] == 3.5
    assert [x["fecha"] for x in ana["capacitaciones"]] == ["2026-03-10", "2026-05-05", "2026-09-01"]
    assert ana["capacitaciones"][0]["estado_firma"] == "PENDIENTE_FIRMA_PAPEL"
    assert por_legajo["999"]["en_padron"] is False
    assert por_legajo["999"]["nombre_completo"] == "Ex Empleado"
    assert [p["legajo"] for p in informe["sin_capacitacion"]] == ["300", "200"]


def test_asistencia_anulada_no_cuenta_y_filtros_por_empresa_y_sector():
    c = cliente()
    tema = c.post("/temas", json={"nombre": "Orden y limpieza", "horas": 1}).json()["id"]
    d = _dictado(c, tema, "2026-04-01")
    _presente(c, d, "100", "Pérez Ana")
    _presente(c, d, "300", "Díaz Carla")
    _presente(c, d, "999", "Ex Empleado")
    c.post(f"/dictados/{d}/asistencias/100/anular", json={"motivo": "Cargada por error"})

    todos = c.get("/informe-anual?anio=2026").json()
    assert [t["legajo"] for t in todos["trabajadores"]] == ["300", "999"]
    assert {p["legajo"] for p in todos["sin_capacitacion"]} == {"100", "200"}

    enav = c.get("/informe-anual?anio=2026&empresa=ENAV").json()
    assert enav["en_padron"] == 2
    assert enav["trabajadores"] == []  # el ex empleado no tiene empresa en el padrón
    assert {p["legajo"] for p in enav["sin_capacitacion"]} == {"100", "200"}

    admin = c.get("/informe-anual?anio=2026&sector=Administraci").json()
    assert [t["legajo"] for t in admin["trabajadores"]] == ["300"]
    assert admin["sin_capacitacion"] == []


def test_sin_padron_informa_el_historial_y_avisa_que_falta_la_lista():
    c = cliente(padron=None)
    tema = c.post("/temas", json={"nombre": "Primeros auxilios", "horas": 3}).json()["id"]
    _presente(c, _dictado(c, tema, "2026-02-02"), "100", "Pérez Ana")
    informe = c.get("/informe-anual?anio=2026").json()
    assert informe["padron_disponible"] is False
    assert informe["sin_capacitacion"] == []
    assert informe["trabajadores"][0]["nombre_completo"] == "Pérez Ana"


def test_informe_valida_anio_y_permiso():
    c = cliente()
    assert c.get("/informe-anual?anio=1800").status_code == 400
    assert c.get("/informe-anual?anio=2026", headers={"X-Perfil-Simulado": "COMPRAS"}).status_code == 403
