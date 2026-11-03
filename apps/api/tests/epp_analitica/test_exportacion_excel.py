from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from suite_juviar.modulos.epp_analitica.api.app import crear_app
from suite_juviar.modulos.epp_analitica.application.servicios import AnalizarEPP
from suite_juviar.modulos.epp_analitica.domain.modelos import MovimientoEPP
from suite_juviar.modulos.epp_analitica.infrastructure.simulados import (
    FuenteEntregasSimulada,
    PreciosSimulados,
)


class FuenteReal(FuenteEntregasSimulada):
    simulada = False


class PreciosReales:
    dueno_dato = "Compras"
    simulada = False

    def obtener(self, item_codigo, fecha):
        return Decimal(100)


NOMBRES = {"68": "Calzado de seguridad", "40": "Guantes", "B-1": "Marca A · Bota", "G-1": "Marca G · Guante",
          "BOD": "Bodega", "OPE": "Operario"}


class Nombres:
    def elemento(self, codigo):
        return NOMBRES.get(codigo, codigo)

    item = sector = puesto = elemento


def mov(n, legajo, elemento, item, motivo="DESGASTE", reclamo=None):
    return MovimientoEPP(str(n), date(2026, 1, 1) + timedelta(days=n * 30), legajo, "BOD", "OPE",
                         elemento, item, 1, reclamo, motivo)


MOVIMIENTOS = [
    mov(0, "10", "68", "B-1", "PRIMERA_ENTREGA"), mov(1, "10", "68", "B-1", "ROTURA", "ROTURA"),
    mov(2, "10", "68", "B-1"), mov(1, "20", "40", "G-1", "PRIMERA_ENTREGA", "TALLE"),
]


def cliente(fuente=None, precios=None):
    servicio = AnalizarEPP(fuente or FuenteReal(MOVIMIENTOS), precios or PreciosReales(), 2)
    return TestClient(crear_app(servicio, nombres=Nombres()),
                      headers={"X-Perfil-Simulado": "COMPRAS", "X-Actor-Simulado": "compras.luis"})


def hojas(contenido):
    libro = load_workbook(BytesIO(contenido))
    return {h.title: [list(f) for f in h.iter_rows(values_only=True)] for h in libro.worksheets}


def test_excel_trae_resumen_reclamos_y_reemplazos_con_nombres():
    r = cliente().get("/exportar", params={"desde": "2026-01-01", "hasta": "2026-12-31"})
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="epp-2026-01-01-2026-12-31.xlsx"'
    libro = hojas(r.content)
    assert list(libro) == ["Resumen", "Reclamos por motivo", "Reemplazos por motivo"]
    resumen = libro["Resumen"]
    assert ["Tipo de elemento", "Todos"] == resumen[3][:2]
    inicio = next(i for i, f in enumerate(resumen) if f[0] == "Tipo de elemento" and f[1] == "Modelo")
    filas = resumen[inicio + 1:]
    assert filas[0][:8] == ["Calzado de seguridad", "Marca A · Bota", "B-1", "Bodega", "Operario", 3, 3, 2]
    assert filas[0][8] == 30.0 and filas[0][9] == 1 and filas[0][10] == 33.3
    assert filas[1][0] == "Guantes" and filas[1][8] == "Sin datos suficientes"
    assert libro["Reclamos por motivo"][1:] == [
        ["Calzado de seguridad", "Marca A · Bota", "Bodega", "Operario", "Rotura", 1],
        ["Guantes", "Marca G · Guante", "Bodega", "Operario", "Talle", 1]]
    assert ["Calzado de seguridad", "Marca A · Bota", "Rotura", 1] in libro["Reemplazos por motivo"]
    assert ["Calzado de seguridad", "Marca A · Bota", "Primera entrega", 1] in libro["Reemplazos por motivo"]


def test_filtra_por_tipo_de_elemento():
    libro = hojas(cliente().get("/exportar", params={"desde": "2026-01-01", "hasta": "2026-12-31",
                                                     "elemento": "40"}).content)
    assert libro["Resumen"][3][:2] == ["Tipo de elemento", "Guantes"]
    assert [f[0] for f in libro["Reemplazos por motivo"][1:]] == ["Guantes"]
    assert all(f[0] == "Guantes" for f in libro["Reclamos por motivo"][1:])


def test_tablero_filtra_por_elemento_y_exportacion_valida():
    c = cliente()
    tablero = c.get("/tablero", params={"desde": "2026-01-01", "hasta": "2026-12-31", "elemento": "68"}).json()
    assert {m["elemento_codigo"] for m in tablero["metricas"]} == {"68"}
    assert c.get("/exportar", params={"desde": "2026-05-01", "hasta": "2026-01-01"}).status_code == 400
    simulada = cliente(precios=PreciosSimulados()).get("/exportar", params={"desde": "2026-01-01", "hasta": "2026-12-31"})
    assert simulada.status_code == 409
    rrhh = c.get("/exportar", params={"desde": "2026-01-01", "hasta": "2026-12-31"},
                 headers={"X-Perfil-Simulado": "RRHH"})
    assert rrhh.status_code == 403


def test_nombres_desde_el_catalogo_y_la_matriz():
    from types import SimpleNamespace as N

    from suite_juviar.modulos.epp_analitica.infrastructure.simulados import NombresDesdePuerto

    catalogo = N(
        obtener_elemento=lambda c: N(producto="Guantes") if c == "40" else None,
        obtener_item=lambda c: N(marca="Marca G", modelo="Nitrilo", talle="SIN_DATO") if c == "G-1" else None,
        nombre_sector=lambda c: c,
    )
    legajos = N(listar_activos=lambda: [N(sector_codigo="BOD", sector="Bodega", puesto_codigo="OPE", puesto="Operario")])
    nombres = NombresDesdePuerto(N(catalogo=catalogo, legajos=legajos))
    assert nombres.elemento("40") == "Guantes" and nombres.elemento("99") == "99"
    assert nombres.item("G-1") == "Marca G · Nitrilo" and nombres.item("X") == "X"
    assert nombres.sector("BOD") == "Bodega" and nombres.puesto("OPE") == "Operario" and nombres.puesto("Z") == "Z"
