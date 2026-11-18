"""Constancia en PDF de un control automático: resultado, fecha y hora, y fuente consultada."""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


class ConstanciaPDF:
    def constancia(self, titulo: str, filas: list[tuple[str, str]], alerta: bool) -> bytes:
        salida = io.BytesIO()
        doc = SimpleDocTemplate(salida, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                                topMargin=18 * mm, bottomMargin=18 * mm, title=titulo,
                                author="Suite Juviar", subject="Control fiscal de ARCA")
        estilos = getSampleStyleSheet()
        normal = estilos["BodyText"]
        tabla = Table([[Paragraph(f"<b>{escape(k)}</b>", normal), Paragraph(escape(v or "—"), normal)]
                       for k, v in filas], colWidths=[55 * mm, 119 * mm])
        estilo = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bfc9c2")),
                  ("VALIGN", (0, 0), (-1, -1), "TOP"),
                  ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f2"))]
        if filas:
            estilo.append(("BACKGROUND", (1, 0), (1, 0),
                           colors.HexColor("#fde8ea") if alerta else colors.HexColor("#e3f1e9")))
        tabla.setStyle(TableStyle(estilo))
        doc.build([
            Paragraph("Suite Juviar · Controles fiscales de ARCA", estilos["Heading4"]),
            Paragraph(escape(titulo), estilos["Heading2"]),
            Spacer(1, 4 * mm), tabla, Spacer(1, 6 * mm),
            Paragraph("Constancia generada por Gestión con la respuesta de ARCA del momento de la consulta.",
                      estilos["Italic"]),
        ])
        return salida.getvalue()
