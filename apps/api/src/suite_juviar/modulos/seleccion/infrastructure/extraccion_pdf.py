"""Lectura PDF real y reglas provisionales, siempre marcadas no verificadas."""

from __future__ import annotations

import io
import re
from typing import ClassVar

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ..domain.modelos import CampoExtraido


class TextoPDF:
    def extraer_texto(self, contenido: bytes) -> str:
        try:
            lector = PdfReader(io.BytesIO(contenido))
            return "\n".join(pagina.extract_text() or "" for pagina in lector.pages)
        except (OSError, PdfReadError, ValueError):
            return ""


class CamposPorReglasProvisorias:
    estado = "SIMULADO_REGLAS_NO_VALIDADAS"

    _patrones: ClassVar[dict[str, tuple[str, ...]]] = {
        "edad_o_fecha_nacimiento": (
            r"(?im)^.*(?:fecha de nacimiento|nacimiento|edad)\s*[:\-]\s*([^\n]+)",
        ),
        "nivel_estudios": (
            r"(?im)^.*(?:estudios|educaci[oó]n|secundari[oa])\s*[:\-]\s*([^\n]+)",
        ),
        "experiencia": (r"(?im)^.*experiencia\s*[:\-]\s*([^\n]+)",),
        "oficio": (r"(?im)^.*(?:oficio|perfil)\s*[:\-]\s*([^\n]+)",),
        "localidad": (r"(?im)^.*(?:localidad|domicilio)\s*[:\-]\s*([^\n]+)",),
        "contacto": (
            r"(?im)^.*[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}.*$",
            r"(?im)^.*(?:tel[eé]fono|celular|contacto)\s*[:\-]\s*([^\n]+)",
        ),
    }

    def extraer_campos(self, texto: str) -> list[CampoExtraido]:
        resultado: list[CampoExtraido] = []
        for nombre, patrones in self._patrones.items():
            coincidencia = next(
                (hallada for patron in patrones if (hallada := re.search(patron, texto))),
                None,
            )
            if coincidencia is None:
                continue
            fragmento = coincidencia.group(0).strip()[:500]
            valor = coincidencia.group(coincidencia.lastindex or 0).strip()[:300]
            resultado.append(
                CampoExtraido(
                    nombre=nombre,
                    valor=valor,
                    fragmento_fuente=fragmento,
                    verificado=False,
                )
            )
        return resultado
