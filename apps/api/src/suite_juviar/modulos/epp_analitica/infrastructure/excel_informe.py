"""Informe de descarte y reemplazo de EPP en Excel, para Compras e Higiene y Seguridad."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from suite_juviar.plataforma.hoja_calculo import escribir

from ..domain.puertos import NombresEPP

MOTIVOS_RECLAMO = {"ROTURA": "Rotura", "DESGASTE_PREMATURO": "Desgaste prematuro", "TALLE": "Talle",
                   "MOLESTIA_USO": "Molestia al usarlo", "DEFECTO_FABRICA": "Defecto de fábrica"}
_NEGRITA = Font(bold=True)
_FONDO = PatternFill("solid", fgColor="E3ECE8")


def _tabla(hoja, fila: int, columnas: tuple[str, ...], anchos: tuple[int, ...], filas: list[tuple]) -> None:
    for i, titulo in enumerate(columnas, start=1):
        celda = escribir(hoja, fila, i, titulo)
        celda.font, celda.fill = _NEGRITA, _FONDO
        hoja.column_dimensions[get_column_letter(i)].width = anchos[i - 1]
    hoja.freeze_panes = hoja.cell(fila + 1, 1)
    for n, valores in enumerate(filas, start=fila + 1):
        for i, valor in enumerate(valores, start=1):
            escribir(hoja, n, i, valor)


def informe_xlsx(datos: dict, nombres: NombresEPP, generado_por: str) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Resumen"
    escribir(hoja, 1, 1, "Informe de descarte y reemplazo de EPP").font = Font(bold=True, size=14)
    filtros = datos["filtros"]
    encabezado = [
        ("Período", f"{datos['desde']:%d/%m/%Y} al {datos['hasta']:%d/%m/%Y}"),
        ("Tipo de elemento", nombres.elemento(filtros["elemento"]) if filtros["elemento"] else "Todos"),
        ("Sector", nombres.sector(filtros["sector"]) if filtros["sector"] else "Todos"),
        ("Puesto", nombres.puesto(filtros["puesto"]) if filtros["puesto"] else "Todos"),
        ("Generado", f"{datetime.now(ZoneInfo('America/Argentina/San_Juan')):%d/%m/%Y %H:%M} por {generado_por}"),
        ("Duración promedio", f"Se calcula con al menos {datos['muestra_minima']} reposiciones por rotura o desgaste"),
    ]
    for n, (etiqueta, valor) in enumerate(encabezado, start=3):
        escribir(hoja, n, 1, etiqueta).font = _NEGRITA
        escribir(hoja, n, 2, valor)
    metricas = sorted(datos["metricas"], key=lambda m: (nombres.elemento(m.elemento_codigo), nombres.item(m.item_codigo),
                                                        nombres.sector(m.sector), nombres.puesto(m.puesto)))
    _tabla(hoja, 3 + len(encabezado) + 1,
           ("Tipo de elemento", "Modelo", "Código", "Sector", "Puesto", "Entregas", "Unidades entregadas",
            "Reposiciones medidas", "Duración promedio (días)", "Reclamos", "% de reclamos"),
           (24, 30, 14, 22, 24, 10, 12, 13, 14, 10, 11),
           [(nombres.elemento(m.elemento_codigo), nombres.item(m.item_codigo), m.item_codigo,
             nombres.sector(m.sector), nombres.puesto(m.puesto), m.muestra_entregas, m.consumo,
             m.muestra_duracion,
             round(m.duracion_promedio_dias, 1) if m.duracion_promedio_dias is not None else "Sin datos suficientes",
             m.reclamos_total, round(m.reclamos_proporcion * 100, 1)) for m in metricas])

    reclamos = libro.create_sheet("Reclamos por motivo")
    _tabla(reclamos, 1, ("Tipo de elemento", "Modelo", "Sector", "Puesto", "Motivo", "Cantidad"),
           (24, 30, 22, 24, 22, 10),
           [(nombres.elemento(m.elemento_codigo), nombres.item(m.item_codigo), nombres.sector(m.sector),
             nombres.puesto(m.puesto), MOTIVOS_RECLAMO.get(motivo, motivo), cantidad)
            for m in metricas for motivo, cantidad in sorted(m.reclamos.items()) if cantidad])

    reemplazos = libro.create_sheet("Reemplazos por motivo")
    _tabla(reemplazos, 1, ("Tipo de elemento", "Modelo", "Motivo de la entrega", "Unidades"), (24, 30, 24, 10),
           [(nombres.elemento(elemento), nombres.item(item), motivo.replace("_", " ").capitalize(), unidades)
            for (elemento, item), motivos in datos["reemplazos"].items()
            for motivo, unidades in sorted(motivos.items())])

    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()
