"""PDF con el detalle de entregas, una fila por descarga.

Es el comprobante que el productor reenvía a su contador o compara contra la
liquidación, así que lleva la misma información que el ticket: fecha, bodega,
CIU, variedad, kilos y azúcar, con los totales al pie.

También arma el comprobante de una sola descarga (DDJJ – Comprobante de Ingreso de Uva), con
el mismo estilo y el mismo pie de documento informativo.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .estadisticas import Entrega, Resumen, formatear_kg
from .turnos import NOMBRE_SEDE

TINTA = colors.HexColor("#0b0b0b")
TINTA_SUAVE = colors.HexColor("#52514e")
CABECERA = colors.HexColor("#1f3b57")
LINEA = colors.HexColor("#d7d6d1")
FONDO_ALTERNO = colors.HexColor("#f4f4f1")
FILAS_POR_PAGINA = 34


def _estilos():
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("t", parent=base["Title"], fontSize=15, textColor=CABECERA,
                                 spaceAfter=2, alignment=0),
        "sub": ParagraphStyle("s", parent=base["Normal"], fontSize=9.5, textColor=TINTA_SUAVE),
        "celda": ParagraphStyle("c", parent=base["Normal"], fontSize=9, textColor=TINTA),
        "num": ParagraphStyle("n", parent=base["Normal"], fontSize=9, textColor=TINTA,
                              alignment=TA_RIGHT),
    }


def generar(
    entregas: list[Entrega],
    resumen: Resumen,
    titular: str,
    cuenta: str,
    periodo: str,
    datos_al: str | None = None,
) -> bytes:
    memoria = io.BytesIO()
    documento = SimpleDocTemplate(
        memoria, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Detalle de cosecha {cuenta}", author="Juviar-ENAV",
    )
    estilo = _estilos()
    partes = [
        Paragraph("Detalle de uva por productor", estilo["titulo"]),
        Paragraph(f"<b>{titular.strip().rstrip('.')}</b> — Cuenta {cuenta}", estilo["sub"]),
        Paragraph(f"Período: {periodo} · Emitido el {datetime.now(UTC):%d/%m/%Y}", estilo["sub"]),
        Spacer(1, 7 * mm),
    ]

    filas = [["Fecha", "Bodega", "CIU", "Variedad", "Kilos", "Azúcar"]]
    for e in sorted(entregas, key=lambda x: (x.fecha, x.ciu)):
        filas.append([
            Paragraph(f"{e.fecha:%d/%m/%Y}", estilo["celda"]),
            Paragraph(e.sede.title() if e.sede else "", estilo["celda"]),
            Paragraph(e.ciu, estilo["celda"]),
            Paragraph(e.variedad or "", estilo["celda"]),
            Paragraph(formatear_kg(e.neto).removesuffix(" kg"), estilo["num"]),
            Paragraph(f"{float(e.azucar):g}" if e.azucar is not None else "—", estilo["num"]),
        ])
    filas.append([
        "", "", "", Paragraph("<b>Total</b>", estilo["celda"]),
        Paragraph(f"<b>{formatear_kg(resumen.total_kg).removesuffix(' kg')}</b>", estilo["num"]),
        Paragraph(f"<b>{resumen.azucar_promedio:g}</b>" if resumen.azucar_promedio
                  else "—", estilo["num"]),
    ])

    tabla = Table(filas, colWidths=[24 * mm, 24 * mm, 30 * mm, 46 * mm, 24 * mm, 20 * mm],
                  repeatRows=1)
    estilo_tabla = [
        ("BACKGROUND", (0, 0), (-1, 0), CABECERA),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINEA),
        ("LINEABOVE", (0, -1), (-1, -1), 0.9, CABECERA),
    ]
    for i in range(2, len(filas) - 1, 2):
        estilo_tabla.append(("BACKGROUND", (0, i), (-1, i), FONDO_ALTERNO))
    tabla.setStyle(TableStyle(estilo_tabla))
    partes.append(tabla)

    resumen_texto = (
        f"{resumen.entregas} entrega{'s' if resumen.entregas != 1 else ''} · "
        f"promedio {formatear_kg(resumen.promedio_por_entrega)}"
    )
    if resumen.azucar_promedio is not None:
        resumen_texto += (
            f" · azúcar entre {resumen.azucar_min:g} y {resumen.azucar_max:g} g/l "
            f"(promedio ponderado por kilos: {resumen.azucar_promedio:g})"
        )
    partes += [Spacer(1, 6 * mm), KeepTogether(Paragraph(resumen_texto, estilo["sub"]))]
    if datos_al:
        partes.append(Paragraph(f"Datos actualizados al {datos_al}.", estilo["sub"]))

    documento.build(partes, onFirstPage=_pie, onLaterPages=_pie)
    return memoria.getvalue()


def _pie(lienzo, documento) -> None:
    lienzo.saveState()
    lienzo.setFont("Helvetica", 7.5)
    lienzo.setFillColor(TINTA_SUAVE)
    lienzo.drawString(18 * mm, 10 * mm, "Juviar-ENAV · documento informativo, no es una liquidación")
    lienzo.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Página {documento.page}")
    lienzo.restoreState()


# --- DDJJ – Comprobante de Ingreso de Uva, por descarga --------------------------------


@dataclass(frozen=True)
class Comprobante:
    """Una descarga de consulta.descarga_publica, con la cuenta y el titular (infra/044)."""

    ciu: str
    fecha: datetime | date
    sede: str
    cuenta: str
    titular: str
    variedad: str | None
    neto: int | None
    azucar: float | None


def nombre_comprobante(comprobante: Comprobante) -> str:
    """Como el bot anterior: DDJJ_CIU_0000017377_20260210.pdf."""
    ciu = re.sub(r"[^0-9A-Za-z]", "", comprobante.ciu).zfill(10)[:20]
    return f"DDJJ_CIU_{ciu}_{comprobante.fecha:%Y%m%d}.pdf"


def generar_comprobante(comprobante: Comprobante, datos_al: str | None = None) -> bytes:
    memoria = io.BytesIO()
    documento = SimpleDocTemplate(
        memoria, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"DDJJ CIU {comprobante.ciu}", author="Juviar-ENAV",
    )
    estilo = _estilos()
    titular = escape(comprobante.titular.strip().rstrip("."))
    fecha = comprobante.fecha
    fecha_texto = f"{fecha:%d/%m/%Y %H:%M}" if isinstance(fecha, datetime) else f"{fecha:%d/%m/%Y}"
    datos = [
        ("Número CIU", escape(comprobante.ciu)),
        ("Fecha", fecha_texto),
        ("Bodega", NOMBRE_SEDE.get(comprobante.sede, comprobante.sede.replace("-", " ").title())),
        ("Cuenta", escape(comprobante.cuenta)),
        ("Titular", titular),
        ("Variedad", escape(comprobante.variedad or "Sin variedad")),
        ("Peso neto", formatear_kg(comprobante.neto)),
    ]
    if comprobante.azucar is not None:
        datos.append(("Azúcar", f"{float(comprobante.azucar):g} g/l"))
    filas = [[Paragraph(f"<b>{clave}</b>", estilo["celda"]), Paragraph(valor, estilo["celda"])]
             for clave, valor in datos]
    tabla = Table(filas, colWidths=[40 * mm, 120 * mm])
    tabla.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINEA),
        ("BACKGROUND", (0, 0), (0, -1), FONDO_ALTERNO),
        ("BOX", (0, 0), (-1, -1), 0.9, CABECERA),
    ]))
    partes = [
        Paragraph("DDJJ – Comprobante de Ingreso de Uva", estilo["titulo"]),
        Paragraph(f"<b>{titular}</b> — Cuenta {escape(comprobante.cuenta)}", estilo["sub"]),
        Paragraph(f"Emitido el {datetime.now(UTC):%d/%m/%Y}", estilo["sub"]),
        Spacer(1, 7 * mm),
        tabla,
        Spacer(1, 6 * mm),
        Paragraph("Copia informativa armada con los datos de báscula de la bodega. "
                  "No reemplaza la declaración presentada ante el INV.", estilo["sub"]),
    ]
    if datos_al:
        partes.append(Paragraph(f"Datos actualizados al {datos_al}.", estilo["sub"]))
    documento.build(partes, onFirstPage=_pie, onLaterPages=_pie)
    return memoria.getvalue()
