"""Lectura PDF real y reglas provisionales, siempre marcadas no verificadas."""

from __future__ import annotations

import io
import re
from typing import ClassVar

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from suite_juviar.plataforma import ocr

from ..domain.modelos import CampoExtraido


_IMAGENES = ((b"\x89PNG", ".png"), (b"\xff\xd8\xff", ".jpg"), (b"RIFF", ".webp"))
MINIMO_TEXTO_PDF = 40  # menos que esto: PDF escaneado, sin capa de texto
MAXIMO_PAGINAS_OCR = 4


class TextoPDF:
    """Texto del currículum: PDF con texto tal cual; foto o PDF escaneado, con OCR dentro del servidor."""

    def __init__(self, leer_imagen=None) -> None:
        self._leer_imagen = leer_imagen or (
            lambda contenido, extension: ocr.leer_texto_imagen(contenido, extension, idioma=_idioma()))

    def extraer_texto(self, contenido: bytes) -> str:
        for firma, extension in _IMAGENES:
            if contenido.startswith(firma):
                return self._leer_imagen(contenido, extension)
        try:
            lector = PdfReader(io.BytesIO(contenido))
            texto = "\n".join(pagina.extract_text() or "" for pagina in lector.pages)
        except (OSError, PdfReadError, ValueError):
            return ""
        if len(texto.strip()) >= MINIMO_TEXTO_PDF:
            return texto
        return texto + "\n" + self._ocr_pdf(contenido)

    def _ocr_pdf(self, contenido: bytes) -> str:
        try:
            import pypdfium2
            documento = pypdfium2.PdfDocument(contenido)
        except Exception:  # noqa: BLE001 - sin el renderizador o PDF roto: queda el texto que hubo
            return ""
        partes = []
        try:
            for indice in range(min(len(documento), MAXIMO_PAGINAS_OCR)):
                imagen = documento[indice].render(scale=2).to_pil()
                salida = io.BytesIO()
                imagen.save(salida, format="PNG")
                partes.append(self._leer_imagen(salida.getvalue(), ".png"))
        except Exception:  # noqa: BLE001 - una página que no se puede dibujar no frena el resto
            pass
        finally:
            documento.close()
        return "\n".join(partes)


_IDIOMA: list[str] = []


def _idioma() -> str:
    if not _IDIOMA:
        _IDIOMA.append(ocr.idioma_disponible())
    return _IDIOMA[0]


class CamposPorReglasProvisorias:
    estado = "SIMULADO_REGLAS_NO_VALIDADAS"

    _patrones: ClassVar[dict[str, tuple[str, ...]]] = {
        "edad_o_fecha_nacimiento": (
            # «Edad: 55», «Edad 55 Años», «Fecha Nac. 28/06/1969»: el separador es opcional.
            r"(?im)^.*?\b(?:fecha\s+de\s+nacimiento|fecha\s+nac\.?|nacimiento|edad)\b\.?[ \t]*[:\-]?[ \t]*(\d[^\n]*)",
        ),
        "nivel_estudios": (
            r"(?im)^.*?\b(?:estudios|educaci[oó]n|formaci[oó]n)\b[ \t]*[:\-]?[ \t]*(\S[^\n]+)",
            # Sin título: la línea que dice el nivel («Secundario completo», «Universitario en curso»).
            r"(?im)^.*?\b((?:primari|secundari|terciari|universitari)[oa]s?\b[^\n]*)",
        ),
        "experiencia": (r"(?im)^.*?\bexperiencia(?:[ \t]+laboral)?\b[ \t]*[:\-]?[ \t]*(?!laboral\b)(\S[^\n]+)",),
        "oficio": (r"(?im)^.*(?:oficio|perfil)\s*[:\-]\s*([^\n]+)",),
        "localidad": (r"(?im)^.*?\b(?:localidad|domicilio|direcci[oó]n)\b[ \t]*[:\-]?[ \t]*(\S[^\n]+)",),
        "contacto": (
            r"(?im)^.*[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}.*$",
            r"(?im)^.*?\b(?:tel[eé]fono|celular|contacto|cel)\b\.?[ \t]*[:\-]?[ \t]*(\+?\d[\d\s\-()]{6,})",
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
