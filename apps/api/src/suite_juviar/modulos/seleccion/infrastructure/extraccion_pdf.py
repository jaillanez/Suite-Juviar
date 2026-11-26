"""Lectura PDF real y reglas provisionales, siempre marcadas no verificadas.

Dos textos distintos, para dos usos distintos:
- la capa de texto del PDF (lo que el PDF trae escrito), que es lo único que se le manda a la IA
  como texto: si no hay capa, la IA recibe la imagen o las páginas, nunca el OCR;
- el texto para las reglas: la capa de texto o, si es una foto o un PDF escaneado, el OCR.
"""

from __future__ import annotations

import io
import math
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any, ClassVar

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from suite_juviar.plataforma import ocr

from ..application.datos_cv import edad_a, hoy
from ..domain.modelos import CampoExtraido

MINIMO_TEXTO_PDF = 40  # menos que esto: PDF escaneado, sin capa de texto
MAXIMO_PAGINAS_OCR = 4
TAMANO_MAXIMO = 15 * 1024 * 1024  # lo mismo que acepta la lectura del correo por adjunto
MAXIMO_PIXELES = 12_000_000  # una página dibujada nunca pasa de esto (≈ A4 a 300 ppp)
MAXIMO_PIXELES_IMAGEN = 4 * MAXIMO_PIXELES  # una foto más grande que esto no se lee (ni se achica)
ESCALA_MINIMA = 0.25  # una página que habría que achicar más que esto es absurda: se saltea
TIEMPO_OCR_TOTAL = 20.0  # segundos de OCR, en total, por documento


def tipo_imagen(contenido: bytes) -> str | None:
    """Extensión de la imagen según su firma completa, o None si no es PNG, JPEG ni WEBP."""
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if contenido.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return ".webp"
    return None


def escala_segura(ancho: float, alto: float, maxima: float) -> float | None:
    """Escala para dibujar la página sin pasar de MAXIMO_PIXELES; None si la página es absurda."""
    if ancho <= 0 or alto <= 0:
        return None
    escala = min(maxima, math.sqrt(MAXIMO_PIXELES / (ancho * alto)))
    return escala if escala >= ESCALA_MINIMA else None


@contextmanager
def _abrir_pdf(contenido: bytes) -> Iterator[Any | None]:
    """El PDF abierto con pypdfium2, con los mismos controles para dibujar páginas y contarlas.
    None si pasa del tamaño máximo, está roto o falta el renderizador."""
    if len(contenido) > TAMANO_MAXIMO:
        yield None
        return
    try:
        import pypdfium2
        documento = pypdfium2.PdfDocument(contenido)
    except Exception:  # noqa: BLE001 - sin el renderizador o PDF roto: no hay páginas
        yield None
        return
    try:
        yield documento
    finally:
        documento.close()


def cantidad_paginas(contenido: bytes) -> int | None:
    """Cuántas páginas tiene el PDF; None si no se puede abrir o pasa del tamaño máximo."""
    with _abrir_pdf(contenido) as documento:
        return None if documento is None else len(documento)


def paginas_png(contenido: bytes, maximo: int, escala: float) -> list[bytes]:
    """Las primeras páginas de un PDF dibujadas como PNG, con tamaño acotado."""
    paginas: list[bytes] = []
    with _abrir_pdf(contenido) as documento:
        if documento is None:
            return paginas
        for indice in range(min(len(documento), maximo)):
            try:
                pagina = documento[indice]
                ancho, alto = pagina.get_size()
                medida = escala_segura(ancho, alto, escala)
                if medida is None:
                    continue
                salida = io.BytesIO()
                pagina.render(scale=medida).to_pil().save(salida, format="PNG")
                paginas.append(salida.getvalue())
            except Exception:  # noqa: BLE001, S112 - una página que no se puede dibujar no frena el resto
                continue
    return paginas


def _achicar_imagen(contenido: bytes) -> bytes:
    """La foto lista para el OCR, o vacío si no se debe leer (falla cerrada).

    El tamaño sale del encabezado, antes de decodificar nada: si no se puede leer o la imagen pasa de
    MAXIMO_PIXELES_IMAGEN, no hay OCR; entre MAXIMO_PIXELES y ese tope, se achica."""
    try:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = min(Image.MAX_IMAGE_PIXELS or MAXIMO_PIXELES_IMAGEN, MAXIMO_PIXELES_IMAGEN)
        with Image.open(io.BytesIO(contenido)) as imagen:
            ancho, alto = imagen.size
            if ancho <= 0 or alto <= 0 or ancho * alto > MAXIMO_PIXELES_IMAGEN:
                return b""
            if ancho * alto <= MAXIMO_PIXELES:
                return contenido
            factor = math.sqrt(MAXIMO_PIXELES / (ancho * alto))
            medida = (max(1, int(ancho * factor)), max(1, int(alto * factor)))
            imagen.draft("RGB", medida)  # JPEG: decodifica ya achicada
            salida = io.BytesIO()
            imagen.convert("RGB").resize(medida).save(salida, format="PNG")
            return salida.getvalue()
    except Exception:  # noqa: BLE001 - imagen ilegible, dañada o bomba de descompresión: sin OCR
        return b""


class TextoPDF:
    """Texto del currículum: PDF con texto tal cual; foto o PDF escaneado, con OCR dentro del servidor."""

    def __init__(self, leer_imagen: Callable[[bytes, str, float], str] | None = None,
                 reloj: Callable[[], float] = time.monotonic) -> None:
        self._leer_imagen = leer_imagen or (
            lambda contenido, extension, segundos: ocr.leer_texto_imagen(
                contenido, extension, idioma=_idioma(), timeout=max(1, int(segundos))))
        self._reloj = reloj

    def capa_texto(self, contenido: bytes) -> str:
        """Lo que el PDF trae escrito. Vacío para fotos y PDF escaneados (no incluye OCR)."""
        if len(contenido) > TAMANO_MAXIMO or tipo_imagen(contenido):
            return ""
        texto = self._texto_pdf(contenido)
        return texto if len(texto.strip()) >= MINIMO_TEXTO_PDF else ""

    def extraer_texto(self, contenido: bytes) -> str:
        """Texto para las reglas: la capa del PDF o, si no la tiene, el OCR."""
        if len(contenido) > TAMANO_MAXIMO:
            return ""
        limite = self._reloj() + TIEMPO_OCR_TOTAL
        if extension := tipo_imagen(contenido):
            imagen = _achicar_imagen(contenido)
            if not imagen:
                return ""
            if imagen is not contenido:
                extension = ".png"  # achicada: siempre sale como PNG
            return self._leer_imagen(imagen, extension, TIEMPO_OCR_TOTAL)
        texto = self._texto_pdf(contenido)
        if len(texto.strip()) >= MINIMO_TEXTO_PDF or not contenido.startswith(b"%PDF"):
            return texto
        partes = [texto]
        for pagina in paginas_png(contenido, MAXIMO_PAGINAS_OCR, 2):
            restante = limite - self._reloj()
            if restante < 1:
                break
            partes.append(self._leer_imagen(pagina, ".png", restante))
        return "\n".join(partes)

    @staticmethod
    def _texto_pdf(contenido: bytes) -> str:
        try:
            lector = PdfReader(io.BytesIO(contenido))
            return "\n".join(pagina.extract_text() or "" for pagina in lector.pages)
        except (OSError, PdfReadError, ValueError):
            return ""


_IDIOMA: list[str] = []


def _idioma() -> str:
    if not _IDIOMA:
        _IDIOMA.append(ocr.idioma_disponible())
    return _IDIOMA[0]


# ---------------------------------------------------------------- reglas provisorias

_VINETA = re.compile(r"^\s*(?:[•·\-–—*►▸▪■□●○◦✓✔➢➤>»+«|]+\s*|[oeº°]\s+(?=[A-ZÁÉÍÓÚÑ]))")
_SEP = r"[ \t]*[:\-–.]?[ \t]*"
_SECCIONES: dict[str, str] = {
    "estudios": r"(?:estudios(?:[ \t]+(?:cursados|realizados|alcanzados|completados|formales))?"
                r"|educaci[oó]n|formaci[oó]n(?:[ \t]+acad[eé]mica)?|nivel[ \t]+(?:educativo|de[ \t]+estudios)"
                r"|datos[ \t]+acad[eé]micos|escolaridad|instrucci[oó]n)",
    "experiencia": r"(?:experiencias?(?:[ \t]+(?:laboral(?:es)?|profesional(?:es)?|de[ \t]+trabajo))?"
                   r"|antecedentes[ \t]+laborales|trayectoria(?:[ \t]+laboral)?|historial[ \t]+laboral"
                   r"|empleos(?:[ \t]+anteriores)?|trabajos(?:[ \t]+(?:realizados|anteriores))?)",
    "otros": r"(?:datos[ \t]+personales|cursos(?:[ \t]+realizados)?|capacitaci[oó]n(?:es)?|habilidades"
             r"|conocimientos(?:[ \t]+\w+)?|idiomas|referencias(?:[ \t]+\w+)?|objetivos?(?:[ \t]+laboral)?"
             r"|perfil(?:[ \t]+(?:profesional|personal|laboral))?|aptitudes|disponibilidad|otros[ \t]+datos"
             r"|informaci[oó]n[ \t]+adicional|licencias?(?:[ \t]+de[ \t]+conducir)?|carnet|intereses)",
}
_ENCABEZADO = {tipo: re.compile(rf"^(?:{patron}){_SEP}(?P<resto>.*)$", re.IGNORECASE)
               for tipo, patron in _SECCIONES.items()}
# Un dato personal («Edad: 55», «Tel.: …») corta la sección en la que esté.
_DATO_PERSONAL = re.compile(
    r"^(?:edad|fecha[ \t]+(?:de[ \t]+)?nac|lugar[ \t]+(?:y[ \t]+fecha[ \t]+)?de[ \t]+nac|domicilio|direcci[oó]n|tel[eé]fono|tel\b|cel"
    r"|contacto|whats|d\.?n\.?i|cuil|cuit|documento|estado[ \t]+civil|nacionalidad|e-?mail|mail|correo"
    r"|localidad|hijos|sexo|g[eé]nero|oficio|profesi[oó]n|ocupaci[oó]n)\b", re.IGNORECASE)
_CLAVE_VALOR = re.compile(r"^[^\W\d][\w .]{1,25}:[ \t]*\S")

_NIVELES = (
    (5, "Posgrado", r"posgrado|postgrado|maestr[ií]a|doctorado|m[aá]ster"),
    (4, "Universitario", r"universitari[oa]s?|universidad|licenciatura|ingenier[ií]a|abogac[ií]a|facultad"),
    (3, "Terciario", r"terciari[oa]s?|profesorado|tecnicatura|instituto[ \t]+superior|t[eé]cnico[ \t]+superior"),
    (2, "Secundario", (r"secundari[oa]s?|polimodal|bachiller(?:ato)?|nivel[ \t]+medio|escuela[ \t]+t[eé]cnica"
                      r"|perito[ \t]+mercantil|ciclo[ \t]+b[aá]sico")),
    (1, "Primario", r"primari[oa]s?|nivel[ \t]+primario|e\.?g\.?b\.?"),
)
_ESTADOS_ESTUDIO = (
    ("incompleto", r"incomplet[oa]s?|sin[ \t]+terminar|no[ \t]+finalizad[oa]|inconclus[oa]|abandonad[oa]"),
    ("en curso", r"en[ \t]+curso|cursando"),
    ("completo", r"(?<![a-z])complet[oa]s?|finalizad[oa]|egresad[oa]|terminad[oa]"),
)
_OFICIOS = re.compile(
    r"\b(?:medio[ \t]+oficial|oficial[ \t]+(?:alba[ñn]il|electricista|plomero|carpintero|pintor|soldador"
    r"|mec[aá]nico|gral\.?|general)|oficial|ayudante(?:[ \t]+de[ \t]+\w+)?|pe[oó]n(?:[ \t]+\w+)?|tractorista"
    r"|soldador(?:a)?|electricista|mec[aá]nic[oa]|chofer|camionero|capataz|jornaler[oa]|operari[oa]"
    r"|alba[ñn]il|plomero|gasista|pintor(?:a)?|carpinter[oa]|herrer[oa]|tornero|administrativ[oa]"
    r"|vendedor(?:a)?|cajer[oa]|repositor(?:a)?|cosechador(?:a)?|podador(?:a)?|regador(?:a)?|encargad[oa]"
    r"|seren[oa]|vigilador(?:a)?|en[oó]log[oa]|bodeguer[oa]|autoelevadorista|montacarguista|maquinista"
    r"|cociner[oa]|moz[oa]|recepcionista|secretari[oa]|contador(?:a)?|auxiliar(?:[ \t]+\w+)?|supervisor(?:a)?"
    r"|t[eé]cnic[oa][ \t]+\w+)\b", re.IGNORECASE)
_OFICIO_DECLARADO = re.compile(
    r"^.*?\b(?:oficio|profesi[oó]n|ocupaci[oó]n|puesto(?:[ \t]+(?:buscado|deseado|al[ \t]+que[ \t]+aspira))?"
    r"|perfil)[ \t]*[:\-–][ \t]*(?P<valor>\S[^\n]*)$", re.IGNORECASE)
_EDAD = re.compile(r"\bedad\b[ \t]*[:\-–.]?[ \t]*(?P<edad>\d{1,2})(?![\d/.\-])(?:[ \t]*a[ñn]os)?", re.IGNORECASE)
_MESES = {m: i for i, m in enumerate(("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                       "septiembre", "octubre", "noviembre", "diciembre"), start=1)}
_ETIQUETA_NACIMIENTO = (r"(?:fecha[ \t]+de[ \t]+nacimiento|fecha[ \t]+de[ \t]+nac\.?|fecha[ \t]+nac(?:imiento)?\.?"
                        r"|f\.?[ \t]*(?:de[ \t]*)?nac\.?|nacid[oa][ \t]+el|naci[oó][ \t]+el|nacimiento)")
_NACIMIENTO = re.compile(
    rf"{_ETIQUETA_NACIMIENTO}[^\d\n]{{0,40}}?(?P<d>\d{{1,2}})[ \t]*[/.\-][ \t]*(?P<m>\d{{1,2}})[ \t]*[/.\-][ \t]*"
    r"(?P<a>\d{4}|\d{2})(?!\d)", re.IGNORECASE)
_NACIMIENTO_LETRAS = re.compile(
    rf"{_ETIQUETA_NACIMIENTO}[^\d\n]{{0,40}}?(?P<d>\d{{1,2}})[ \t]+de[ \t]+(?P<m>[a-záéíóú]+)[ \t]+(?:de[ \t]+)?"
    r"(?P<a>\d{4})", re.IGNORECASE)
_LOCALIDAD = re.compile(
    r"^(?:localidad|ciudad|departamento|lugar[ \t]+de[ \t]+residencia|residencia|reside[ \t]+en|vive[ \t]+en)"
    r"\b[ \t]*[:\-–]?[ \t]*(?P<valor>\S[^\n]*)$", re.IGNORECASE)
_DOMICILIO = re.compile(r"^.*?\b(?:domicilio|direcci[oó]n|dir\.)[ \t]*[:\-–]?[ \t]*(?P<valor>[^\n]*)$",
                        re.IGNORECASE)
_LUGARES = re.compile(
    r"\b(?:san[ \t]+juan|capital|chimbas|rawson|rivadavia|santa[ \t]+luc[ií]a|pocito|caucete|9[ \t]+de[ \t]+julio"
    r"|nueve[ \t]+de[ \t]+julio|25[ \t]+de[ \t]+mayo|sarmiento|angaco|san[ \t]+mart[ií]n|albard[oó]n|zonda|ullum"
    r"|iglesia|j[aá]chal|calingasta|valle[ \t]+f[eé]rtil|mendoza|provincia|barrio|b[°º]|villa)\b", re.IGNORECASE)
_MAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_TELEFONO = re.compile(r"(?<![\d/])\+?\d[\d \t\-().]{6,18}\d(?![\d/])")
_ETIQUETA_TELEFONO = re.compile(r"\b(?:tel[eé]fonos?|tel|cel(?:ular)?|m[oó]vil|contacto|whats\s*app|wsp|wa)\b",
                                re.IGNORECASE)
_NO_TELEFONO = re.compile(r"\b(?:d\.?n\.?i|cuil|cuit|documento|c\.?p\.?|c[oó]digo[ \t]+postal|fecha|nac)\b",
                          re.IGNORECASE)


def _limpiar(linea: str) -> str:
    return _VINETA.sub("", linea).strip()


def _secciones(lineas: list[str]) -> dict[str, list[tuple[str, list[str]]]]:
    """Cada sección encontrada: (línea del título, líneas que siguen) hasta el próximo título."""
    resultado: dict[str, list[tuple[str, list[str]]]] = {"estudios": [], "experiencia": []}
    actual: list[str] | None = None
    en_linea = False  # «Estudios: Secundario completo»: el dato vino en la misma línea del título
    for linea in lineas:
        limpia = _limpiar(linea)
        if not limpia:
            continue
        tipo = next((t for t, patron in _ENCABEZADO.items()
                     if len(limpia) <= 160 and (hallado := patron.match(limpia))
                     and _es_titulo(limpia, hallado.group("resto"))), None)
        if tipo:
            actual = None
            if tipo in resultado:
                resto = _ENCABEZADO[tipo].match(limpia).group("resto").strip()
                actual = [resto] if resto else []
                en_linea = bool(resto)
                resultado[tipo].append((linea.strip(), actual))
            continue
        if _DATO_PERSONAL.match(limpia) or (en_linea and _CLAVE_VALOR.match(limpia)):
            actual = None
            continue
        if actual is not None and len(actual) < 15:
            actual.append(linea.strip())
    return resultado


def _es_titulo(linea: str, resto: str) -> bool:
    # «Experiencia laboral», «ESTUDIOS:», «Estudios: Secundario completo». No «Experiencia en bodega 4 años»
    # sin separador, que igual se toma como dato de la sección.
    return bool(resto.strip()) or len(linea) <= 60


def _vinetas(lineas: list[str]) -> list[str]:
    """Une las líneas en ítems: cada viñeta es uno; sin viñetas, cada línea es uno."""
    con_vineta = any(_limpiar(linea) != linea.strip() for linea in lineas)
    items: list[str] = []
    for linea in lineas:
        limpia = _limpiar(linea)
        if not limpia:
            continue
        if con_vineta and items and limpia == linea.strip():
            items[-1] = f"{items[-1]} {limpia}"
        else:
            items.append(limpia)
    return items


def _fragmento(lineas: list[str]) -> str:
    """Las líneas leídas, sin repetir la que ya está dentro del título («Estudios: Secundario completo»)."""
    unicas = list(dict.fromkeys(lineas))
    return " / ".join(x for x in unicas if not any(x != otra and x in otra for otra in unicas))


def _nivel_de(linea: str) -> tuple[int, str, str | None] | None:
    for orden, nombre, patron in _NIVELES:
        if re.search(rf"\b(?:{patron})", linea, re.IGNORECASE):
            estado = next((e for e, p in _ESTADOS_ESTUDIO if re.search(p, linea, re.IGNORECASE)), None)
            return orden, nombre, estado
    return None


class CamposPorReglasProvisorias:
    """Reglas para los formatos típicos de CV: título de sección y datos debajo, viñetas, etiquetas sin «:»."""

    estado = "SIMULADO_REGLAS_NO_VALIDADAS"
    _ORDEN: ClassVar[tuple[str, ...]] = (
        "edad_o_fecha_nacimiento", "nivel_estudios", "experiencia", "oficio", "localidad", "contacto")

    def __init__(self, hoy: Callable[[], date] = hoy) -> None:
        self._hoy = hoy

    def extraer_campos(self, texto: str) -> list[CampoExtraido]:
        lineas = [linea for linea in texto.replace("\r", "").split("\n") if linea.strip()]
        secciones = _secciones(lineas)
        experiencia = self._experiencia(secciones["experiencia"])
        hallados = {
            "edad_o_fecha_nacimiento": self._edad(lineas),
            "nivel_estudios": self._estudios(lineas, secciones["estudios"]),
            "experiencia": experiencia,
            "oficio": self._oficio(lineas, secciones["experiencia"]),
            "localidad": self._localidad(lineas),
            "contacto": self._contacto(lineas),
        }
        return [
            CampoExtraido(nombre=nombre, valor=valor[:300], fragmento_fuente=fragmento[:500], verificado=False)
            for nombre in self._ORDEN
            if (dato := hallados[nombre]) and (valor := dato[0].strip()) and (fragmento := dato[1].strip())
        ]

    def _edad(self, lineas: list[str]) -> tuple[str, str] | None:
        edad = fecha = None
        fragmentos = []
        for linea in lineas:
            if edad is None and (hallada := _EDAD.search(linea)):
                edad = int(hallada.group("edad"))
                fragmentos.append(linea.strip())
            if fecha is None and (hallada := _NACIMIENTO.search(linea) or _NACIMIENTO_LETRAS.search(linea)):
                fecha = self._fecha(hallada)
                if fecha:
                    fragmentos.append(linea.strip())
        if fecha:
            calculada = edad_a(fecha, self._hoy())
            texto_fecha = fecha.strftime("%d/%m/%Y")
            if edad is not None and abs(edad - calculada) > 1:
                # El CV es viejo o la fecha está mal escrita: se muestran las dos cosas tal cual.
                return f"{calculada} años hoy (nació el {texto_fecha}; el CV dice {edad})", \
                    " / ".join(dict.fromkeys(fragmentos))
            return f"{calculada} años (nació el {texto_fecha})", " / ".join(dict.fromkeys(fragmentos))
        if edad is not None and 14 <= edad <= 99:
            return f"{edad} años", fragmentos[0]
        return None

    def _fecha(self, hallada: re.Match[str]) -> date | None:
        dia, mes, anio = hallada.group("d"), hallada.group("m"), hallada.group("a")
        mes_numero = int(mes) if mes.isdigit() else _MESES.get(mes.casefold())
        anio_numero = int(anio)
        if len(anio) == 2:
            anio_numero += 1900 if anio_numero > self._hoy().year % 100 else 2000
        try:
            fecha = date(anio_numero, mes_numero or 0, int(dia))
        except ValueError:
            return None
        return fecha if 14 <= edad_a(fecha, self._hoy()) <= 99 else None

    @staticmethod
    def _estudios(lineas: list[str], secciones: list[tuple[str, list[str]]]) -> tuple[str, str] | None:
        candidatas = [(titulo, cuerpo) for titulo, cuerpo in secciones]
        # Sin título de sección: las líneas que empiezan con el nivel («Secundario: Incompleto»).
        sueltas = [linea.strip() for linea in lineas if re.match(
            rf"^(?:{'|'.join(p for _, _, p in _NIVELES)})\b", _limpiar(linea), re.IGNORECASE)]
        mejor: tuple[int, str, str | None, str] | None = None
        usadas: list[str] = []
        for linea in [x for _, cuerpo in candidatas for x in cuerpo] + sueltas:
            nivel = _nivel_de(linea)
            if nivel is None:
                continue
            usadas.append(linea)
            if mejor is None or nivel[0] > mejor[0] or (nivel[0] == mejor[0] and mejor[2] is None and nivel[2]):
                mejor = (*nivel, linea)
        if mejor:
            _orden, nombre, estado, _ = mejor
            titulos = [titulo for titulo, cuerpo in candidatas if any(u in cuerpo for u in usadas)]
            fragmento = _fragmento(titulos + usadas)
            return (f"{nombre} {estado}" if estado else nombre), fragmento
        for titulo, cuerpo in candidatas:
            if cuerpo:
                return _limpiar(cuerpo[0]), _fragmento([titulo, *cuerpo[:3]])
        return None

    @staticmethod
    def _experiencia(secciones: list[tuple[str, list[str]]]) -> tuple[str, str] | None:
        for titulo, cuerpo in secciones:
            items = _vinetas(cuerpo)
            if items:
                return "; ".join(items), _fragmento([titulo, *cuerpo[:8]])
        return None

    @staticmethod
    def _oficio(lineas: list[str], secciones: list[tuple[str, list[str]]]) -> tuple[str, str] | None:
        for linea in lineas:
            if (hallado := _OFICIO_DECLARADO.match(_limpiar(linea))) and len(hallado.group("valor")) <= 80:
                return hallado.group("valor").strip(), linea.strip()
        # Sin oficio declarado: el puesto escrito en la experiencia, sólo si nombra un oficio conocido.
        oficios: dict[str, str] = {}
        fragmentos: list[str] = []
        for _, cuerpo in secciones:
            for item in _vinetas(cuerpo):
                partes = re.findall(r"\(([^)]+)\)", item) or re.split(r"\s+[-–—|]\s+|\s+como\s+|:\s+", item)
                for parte in partes:
                    if _OFICIOS.search(parte):
                        valor = re.sub(r"[\s.,;]+$", "", parte.strip()) + ("." if parte.strip().endswith(".") else "")
                        clave = re.sub(r"\W", "", valor.casefold())
                        oficios.setdefault(clave, valor[:1].upper() + valor[1:])
                        fragmentos.append(item)
                        break
        if oficios:
            return ", ".join(list(oficios.values())[:3]), " / ".join(dict.fromkeys(fragmentos))
        return None

    @staticmethod
    def _localidad(lineas: list[str]) -> tuple[str, str] | None:
        for linea in lineas:
            if hallada := _LOCALIDAD.match(_limpiar(linea)):
                return hallada.group("valor").strip(), linea.strip()
        for indice, linea in enumerate(lineas):
            if not (hallada := _DOMICILIO.match(_limpiar(linea))):
                continue
            valor = hallada.group("valor").strip()
            siguiente = _limpiar(lineas[indice + 1]) if indice + 1 < len(lineas) else ""
            sigue_lugar = (siguiente and ":" not in siguiente and len(siguiente) <= 60
                           and not _DATO_PERSONAL.match(siguiente) and not _MAIL.search(siguiente)
                           and not any(p.match(siguiente) for p in _ENCABEZADO.values()))
            if not valor and sigue_lugar:
                return siguiente, f"{linea.strip()} / {lineas[indice + 1].strip()}"
            if valor and sigue_lugar and _LUGARES.search(siguiente) and not _LUGARES.search(valor):
                return f"{valor}, {siguiente}", f"{linea.strip()} / {lineas[indice + 1].strip()}"
            if valor:
                return valor, linea.strip()
        return None

    @staticmethod
    def _contacto(lineas: list[str]) -> tuple[str, str] | None:
        telefonos: list[str] = []
        mails: list[str] = []
        fragmentos: list[str] = []
        for linea in lineas:
            encontrados = _MAIL.findall(linea)
            sin_mail = _MAIL.sub(" ", linea)
            etiquetada = bool(_ETIQUETA_TELEFONO.search(sin_mail))
            if not _NO_TELEFONO.search(sin_mail) or etiquetada:
                for numero in _TELEFONO.findall(sin_mail):
                    digitos = re.sub(r"\D", "", numero)
                    if re.fullmatch(r"\s*(?:19|20)\d{2}\s*[-–]\s*(?:19|20)\d{2}\s*", numero):
                        continue  # «2015 - 2018»: un período, no un teléfono
                    if re.search(r"\d{1,2}\.\d{3}\.\d{3}", numero):
                        continue  # 30.123.456: un DNI
                    if (etiquetada and 7 <= len(digitos) <= 13) or (10 <= len(digitos) <= 13):
                        telefonos.append(numero.strip())
                        encontrados.append(numero)
            if encontrados:
                mails.extend(m for m in _MAIL.findall(linea))
                fragmentos.append(linea.strip())
        valores = list(dict.fromkeys(telefonos[:2])) + list(dict.fromkeys(mails[:2]))
        if not valores:
            return None
        return " · ".join(valores), " / ".join(dict.fromkeys(fragmentos))
