from dataclasses import dataclass
from datetime import date
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from suite_juviar.modulos.salud.api.app import crear_app
from suite_juviar.modulos.salud.application.servicios import GestionarSalud
from suite_juviar.modulos.salud.infrastructure.simulados import (
    AdjuntosSaludCifradosMemoria,
    CatalogoDiagnosticoSimulado,
    FuenteLaboralSimulada,
    SaludMemoria,
)


@dataclass(frozen=True)
class Persona:
    legajo: str
    nombre_completo: str
    empresa: str
    sector: str
    puesto: str


class Personas:
    simulada = True

    def obtener(self, legajo):
        return Persona("10", "Pérez, Ana", "ENAV", "Bodega", "Operaria") if legajo == "10" else None


def preparar():
    s = GestionarSalud(CatalogoDiagnosticoSimulado(), SaludMemoria(), AdjuntosSaludCifradosMemoria(b"0" * 32),
                       FuenteLaboralSimulada(), Personas())
    for desde, hasta, resumen in ((date(2026, 3, 1), date(2026, 3, 20), "Reposo prolongado"),
                                  (date(2025, 11, 5), date(2025, 11, 6), "Control")):
        s.cargar("10", "MUESTRA-RESP", desde, hasta, (hasta - desde).days + 1, "Dra. Prueba",
                 "escaneo.pdf", b"PDF", resumen, "IN_ITINERE")
    s.cargar("20", "MUESTRA-RESP", date(2026, 1, 1), date(2026, 1, 1), 1, "Dr. Otro", "e.pdf", b"PDF")
    return s, TestClient(crear_app(s), headers={"X-Perfil-Simulado": "MEDICO", "X-Actor-Simulado": "dra.medica"})


def _filas(contenido):
    hoja = load_workbook(BytesIO(contenido)).active
    return [list(fila) for fila in hoja.iter_rows(values_only=True)]


def test_expediente_en_excel_cronologico_con_total_y_auditado():
    s, c = preparar()
    r = c.get("/expedientes/10/excel")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="ausentismo-10.xlsx"'
    filas = _filas(r.content)
    assert filas[0][0] == "DATOS SIMULADOS — SIN VALIDEZ"
    datos = {f[0]: f[1] for f in filas if f[0] and f[1] is not None}
    assert datos["Apellido y nombre"] == "Pérez, Ana" and datos["Total de días de reposo"] == 22
    assert datos["Período"] == "Todo el historial" and datos["Certificados"] == 2
    encabezado = next(i for i, f in enumerate(filas) if f[0] == "Desde")
    detalle = filas[encabezado + 1:encabezado + 3]
    assert [f[1].date() for f in detalle] == [date(2025, 11, 6), date(2026, 3, 20)]
    assert detalle[1][2] == 20 and detalle[1][5] == "In itinere" and detalle[1][7] == "Reposo prolongado"
    assert filas[encabezado + 3][1:3] == ["Total", 22]
    assert any(x.accion == "EXPORTACION_EXPEDIENTE" and x.legajo == "10" and x.actor == "dra.medica"
               for x in s.repositorio.listar_auditoria())


def test_expediente_filtra_periodo_y_valida():
    _, c = preparar()
    filas = _filas(c.get("/expedientes/10/excel?desde=2026-01-01").content)
    datos = {f[0]: f[1] for f in filas if f[0] and f[1] is not None}
    assert datos["Certificados"] == 1 and datos["Período"] == "Del 01/01/2026 a hoy"
    assert c.get("/expedientes/10/excel?desde=2026-05-01&hasta=2026-01-01").status_code == 400
    assert c.get("/expedientes/99/excel").status_code == 404
    rrhh = c.get("/expedientes/10/excel", headers={"X-Perfil-Simulado": "RRHH"})
    assert rrhh.status_code == 403


def test_texto_con_igual_no_se_vuelve_formula_y_la_consulta_vacia_se_audita():
    s, c = preparar()
    s.cargar("10", "MUESTRA-RESP", date(2026, 8, 1), date(2026, 8, 1), 1, "=HYPERLINK(\"http://x\")",
             "e.pdf", b"PDF", "=1+1")
    hoja = load_workbook(BytesIO(c.get("/expedientes/10/excel").content)).active
    celdas = [celda for fila in hoja.iter_rows() for celda in fila if celda.value in ("=1+1", '=HYPERLINK("http://x")')]
    assert len(celdas) == 2 and all(celda.data_type == "s" for celda in celdas)
    assert c.get("/expedientes/77/excel").status_code == 404
    assert any(x.legajo == "77" and x.accion == "EXPORTACION_EXPEDIENTE" for x in s.repositorio.listar_auditoria())
