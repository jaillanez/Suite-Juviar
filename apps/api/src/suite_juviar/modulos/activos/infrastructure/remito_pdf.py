"""Remito de salida en PDF para imprimir: con la firma del celular o con el lugar para firmar a mano."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape as e
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..domain.modelos import BODEGAS
from ..domain.remitos import ModoFirma, Remito

_ZONA = ZoneInfo("America/Argentina/San_Juan")
_VERDE = colors.HexColor("#1F5C45")


def _fecha(momento: datetime | None) -> str:
    return momento.astimezone(_ZONA).strftime("%d/%m/%Y %H:%M") if momento else ""


def remito_pdf(remito: Remito) -> bytes:
    estilos = getSampleStyleSheet()
    normal = ParagraphStyle("n", parent=estilos["Normal"], fontSize=10, leading=13)
    celda = ParagraphStyle("c", parent=normal, fontSize=9.5, leading=12)
    blanca = ParagraphStyle("b", parent=celda, textColor=colors.white, fontName="Helvetica-Bold")
    titulo = ParagraphStyle("t", parent=estilos["Title"], fontSize=18, textColor=_VERDE, alignment=0)
    h = [Paragraph(f"Remito de salida N.º {remito.numero:06d}", titulo),
         Paragraph(f"Bodega <b>{BODEGAS.get(remito.bodega, '')}</b> · Emitido {_fecha(remito.creado_en)}", normal),
         Spacer(1, 6),
         Paragraph(f"<b>Destino:</b> {e(remito.destino)}", normal),
         Paragraph(f"<b>Motivo:</b> {e(remito.motivo)}", normal), Spacer(1, 8)]
    filas = [[Paragraph(t, blanca) for t in ("Código", "Descripción", "Cant.", "Volvió")]]
    for item in remito.items:
        filas.append([Paragraph(e(item.codigo or "Sin código"), celda), Paragraph(e(item.descripcion), celda),
                      Paragraph(str(item.cantidad), celda), Paragraph(_fecha(item.volvio_en), celda)])
    tabla = Table(filas, colWidths=[30 * mm, 100 * mm, 15 * mm, 29 * mm], repeatRows=1)
    tabla.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), _VERDE),
                               ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D6D0")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    h += [tabla, Spacer(1, 18)]
    firma = remito.firma
    if firma and firma.modo is ModoFirma.CELULAR and firma.imagen:
        bloque = [Image(BytesIO(firma.imagen), width=60 * mm, height=22 * mm, kind="proportional"),
                  Paragraph(f"Firmado en el celular por {e(firma.por)} el {_fecha(firma.en)}", celda)]
    else:
        autorizado = f"Autorizado en Gestión por {e(firma.por)} el {_fecha(firma.en)}" if firma else "SIN AUTORIZAR"
        bloque = [Spacer(1, 20), Paragraph("_" * 40, normal),
                  Paragraph("Firma y aclaración del Encargado de Mantenimiento", celda), Paragraph(autorizado, celda)]
    salida = [Spacer(1, 20), Paragraph("_" * 40, normal), Paragraph("Guardia: firma, fecha y hora de salida", celda)]
    if remito.salio_en:
        salida.append(Paragraph(f"Salida marcada por {e(remito.salio_por)} el {_fecha(remito.salio_en)}", celda))
    pie = Table([[bloque, salida]], colWidths=[87 * mm, 87 * mm])
    pie.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    h += [pie, Spacer(1, 14),
          Paragraph("Ningún equipo ni herramienta sale de la planta sin este remito autorizado por el "
                    "Encargado de Mantenimiento.", celda)]
    salida_pdf = BytesIO()
    SimpleDocTemplate(salida_pdf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                      bottomMargin=16 * mm, title=f"Remito {remito.numero}").build(h)
    return salida_pdf.getvalue()
