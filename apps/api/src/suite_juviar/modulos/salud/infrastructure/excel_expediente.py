"""Expediente de ausentismo en Excel para los asesores legales."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ..domain.modelos import MARCA_SIMULADA

TIPOS_ACCIDENTE = {
    "NO_INFORMADO": "No informado",
    "NO_ES_ACCIDENTE": "No es accidente",
    "ACCIDENTE_LABORAL": "Accidente laboral",
    "IN_ITINERE": "In itinere",
    "ACCIDENTE_A_REVISAR": "Accidente a revisar",
}
COLUMNAS = ("Desde", "Hasta", "Días de reposo", "Código", "Diagnóstico", "Tipo de accidente",
            "Profesional", "Resumen")
ANCHOS = (12, 12, 10, 16, 34, 20, 26, 60)


def expediente_xlsx(expediente: dict, generado_por: str) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Ausentismo"
    negrita = Font(bold=True)
    persona = expediente["persona"]
    fila = 1
    if expediente["simulado"]:
        hoja.cell(fila, 1, MARCA_SIMULADA).font = Font(bold=True, color="FFFFFF")
        hoja.cell(fila, 1).fill = PatternFill("solid", fgColor="B00020")
        fila += 2
    hoja.cell(fila, 1, "Expediente de ausentismo").font = Font(bold=True, size=14)
    fila += 2
    desde, hasta = expediente["desde"], expediente["hasta"]
    periodo = (f"Del {desde:%d/%m/%Y}" if desde else "Desde el inicio") + (f" al {hasta:%d/%m/%Y}" if hasta else " a hoy")
    if not desde and not hasta:
        periodo = "Todo el historial"
    datos = [
        ("Legajo", expediente["legajo"]),
        ("Apellido y nombre", persona.nombre_completo if persona else ""),
        ("Empresa", persona.empresa if persona else ""),
        ("Sector", persona.sector if persona else ""),
        ("Puesto", persona.puesto if persona else ""),
        ("Período", periodo),
        ("Certificados", len(expediente["certificados"])),
        ("Total de días de reposo", expediente["total_dias"]),
        ("Generado", f"{datetime.now(ZoneInfo('America/Argentina/San_Juan')):%d/%m/%Y %H:%M} por {generado_por}"),
    ]
    for etiqueta, valor in datos:
        hoja.cell(fila, 1, etiqueta).font = negrita
        hoja.cell(fila, 2, valor)
        fila += 1
    fila += 1
    encabezado = fila
    for columna, titulo in enumerate(COLUMNAS, start=1):
        celda = hoja.cell(fila, columna, titulo)
        celda.font = negrita
        celda.fill = PatternFill("solid", fgColor="E3ECE8")
    for item in expediente["certificados"]:
        fila += 1
        c = item["certificado"]
        valores = (c.desde, c.hasta, c.dias, c.diagnostico_codigo, item["diagnostico"],
                   TIPOS_ACCIDENTE.get(c.tipo_accidente, c.tipo_accidente), c.profesional, c.resumen)
        for columna, valor in enumerate(valores, start=1):
            celda = hoja.cell(fila, columna, valor)
            if columna <= 2:
                celda.number_format = "DD/MM/YYYY"
            if columna == len(COLUMNAS):
                celda.alignment = Alignment(wrap_text=True, vertical="top")
    fila += 1
    hoja.cell(fila, 2, "Total").font = negrita
    hoja.cell(fila, 3, expediente["total_dias"]).font = negrita
    for columna, ancho in enumerate(ANCHOS, start=1):
        hoja.column_dimensions[get_column_letter(columna)].width = ancho
    hoja.freeze_panes = hoja.cell(encabezado + 1, 1)
    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()
