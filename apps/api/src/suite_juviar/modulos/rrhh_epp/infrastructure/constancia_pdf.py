"""Constancia PDF individual de prueba con marca visible de invalidez legal."""

from __future__ import annotations

import base64
import binascii
import hashlib
from datetime import UTC, datetime
from io import BytesIO

from PIL import Image as PILImage
from PIL import UnidentifiedImageError
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as PDFImage
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..domain.modelos_mvp import DocumentoConstancia, Entrega


class GeneradorConstanciaPDFSimulada:
    """Genera un original imprimible; no aplica firma digital de la empresa."""

    def generar(self, entrega: Entrega) -> DocumentoConstancia:
        salida = BytesIO()
        documento = SimpleDocTemplate(
            salida,
            pagesize=landscape(A4),
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=10 * mm,
            bottomMargin=10 * mm,
            title=f"RD 062/11 - Entrega EPP {entrega.id}",
            author="ENAV - Suite Juviar",
            subject="Constancia individual de entrega de ropa de trabajo y EPP",
        )
        estilos = getSampleStyleSheet()
        normal = ParagraphStyle("normal_epp", parent=estilos["BodyText"], fontSize=7, leading=9)
        centro = ParagraphStyle(
            "centro_epp", parent=normal, alignment=TA_CENTER, fontSize=8, leading=10
        )
        titulo = ParagraphStyle(
            "titulo_epp", parent=centro, fontSize=13, leading=15, spaceAfter=4 * mm
        )
        alerta = ParagraphStyle("alerta_epp", parent=centro, textColor=colors.white)
        historia: list[object] = [
            Table(
                [[
                    Paragraph("<b>DOCUMENTO DE PRUEBA - SIN VALIDEZ LEGAL</b>", alerta),
                ]],
                colWidths=[273 * mm],
                style=TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#A8400C")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#792D09")),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]),
            ),
            Spacer(1, 3 * mm),
            Paragraph("<b>ENTREGA DE ROPA DE TRABAJO Y EPP</b>", titulo),
            Paragraph(
                f"RD 062/11 - Comprobante {entrega.id} - "
                f"{entrega.fecha_entrega.strftime('%d/%m/%Y')}",
                centro,
            ),
            Spacer(1, 3 * mm),
            Table(
                [[
                    Paragraph(
                        f"<b>Trabajador:</b> {entrega.legajo.nombre_completo}<br/>"
                        f"<b>DNI:</b> {entrega.legajo.dni} - <b>Legajo:</b> {entrega.legajo.legajo}",
                        normal,
                    ),
                    Paragraph(
                        f"<b>Puesto:</b> {entrega.legajo.puesto}<br/>"
                        f"<b>Sector:</b> {entrega.legajo.sector} - "
                        f"<b>Empresa:</b> {entrega.legajo.empresa}",
                        normal,
                    ),
                ]],
                colWidths=[136.5 * mm, 136.5 * mm],
                style=TableStyle([
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("PADDING", (0, 0), (-1, -1), 5),
                ]),
            ),
            Spacer(1, 3 * mm),
        ]
        filas: list[list[object]] = [[
            Paragraph("<b>Producto</b>", centro),
            Paragraph("<b>Ítem / Tipo / Modelo</b>", centro),
            Paragraph("<b>Marca</b>", centro),
            Paragraph("<b>Talle / Color</b>", centro),
            Paragraph("<b>Certificación</b>", centro),
            Paragraph("<b>Cant.</b>", centro),
            Paragraph("<b>Fecha</b>", centro),
        ]]
        for linea in entrega.lineas:
            filas.append([
                Paragraph(linea.producto, normal),
                Paragraph(
                    f"{linea.item_codigo}<br/>{linea.tipo_modelo}<br/><b>{linea.estado_item}</b>",
                    normal,
                ),
                Paragraph(linea.marca, normal),
                Paragraph(f"{linea.talle} / {linea.color}", normal),
                Paragraph(
                    ("SI" if linea.posee_certificacion else "NO")
                    + (f" - {linea.certificacion}" if linea.certificacion else ""),
                    normal,
                ),
                Paragraph(str(linea.cantidad), centro),
                Paragraph(entrega.fecha_entrega.strftime("%d/%m/%Y"), centro),
            ])
        historia.append(
            Table(
                filas,
                repeatRows=1,
                colWidths=[38 * mm, 70 * mm, 30 * mm, 32 * mm, 55 * mm, 18 * mm, 30 * mm],
                style=TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                    ("BOX", (0, 0), (-1, -1), 0.7, colors.black),
                    ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]),
            )
        )
        historia.extend([
            Spacer(1, 5 * mm),
            Table(
                [[self._firma(entrega), Paragraph(
                    f"<b>Método:</b> {entrega.firma_trabajador.metodo}<br/>"
                    f"<b>Sello:</b> {entrega.firma_trabajador.sello_tiempo.isoformat()}<br/>"
                    f"<b>Registró:</b> {entrega.usuario_deposito}<br/>"
                    "<b>Firma digital empresa:</b> PENDIENTE - motor real no disponible",
                    normal,
                )]],
                colWidths=[136.5 * mm, 136.5 * mm],
                style=TableStyle([
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("PADDING", (0, 0), (-1, -1), 6),
                ]),
            ),
            Spacer(1, 3 * mm),
            Paragraph(
                "El archivo conserva este original, pero no está firmado digitalmente por la empresa. "
                "Se imprime y firma en papel hasta habilitar plataforma/firma.",
                centro,
            ),
        ])
        documento.build(historia)
        contenido = salida.getvalue()
        return DocumentoConstancia(
            id_entrega=entrega.id,
            contenido=contenido,
            sha256=hashlib.sha256(contenido).hexdigest(),
            generado_en=datetime.now(UTC),
            firmado=False,
            simulado=True,
        )

    @staticmethod
    def _firma(entrega: Entrega) -> object:
        evidencia = entrega.firma_trabajador.evidencia
        if evidencia.startswith("data:image") and "," in evidencia:
            try:
                contenido = base64.b64decode(evidencia.split(",", 1)[1], validate=True)
                PILImage.open(BytesIO(contenido)).verify()
                imagen = PDFImage(BytesIO(contenido))
                imagen.drawHeight = 24 * mm
                imagen.drawWidth = 70 * mm
                return imagen
            except (binascii.Error, OSError, UnidentifiedImageError, ValueError):
                return Paragraph(
                    "Firma del trabajador: evidencia simulada inválida",
                    getSampleStyleSheet()["BodyText"],
                )
        return Paragraph("Firma del trabajador: evidencia simulada conservada", getSampleStyleSheet()["BodyText"])
