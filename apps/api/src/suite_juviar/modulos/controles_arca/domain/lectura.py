"""Lectura de la factura del proveedor desde una foto tomada con el celular.

- Con QR (factura electrónica, RG 4291 de ARCA): el QR es una dirección
  ``https://www.afip.gob.ar/fe/qr/?p=<JSON en base64>`` con los datos del comprobante.
  Se decodifica y se valida acá; esos datos son los que ARCA autorizó y se controlan
  sin pedir confirmación.
- Sin QR (factura vieja, controlador fiscal, papel o QR ilegible): se lee el texto de
  la foto y con reglas se sacan los datos que se puedan. Esos datos son una propuesta:
  la persona los confirma o corrige antes de controlar.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import unquote, urlsplit

from .modelos import TIPOS_COMPROBANTE, cuit_valido

# El QR sólo se acepta de los sitios de ARCA (antes AFIP).
HOSTS_QR = frozenset({"afip.gob.ar", "www.afip.gob.ar", "arca.gob.ar", "www.arca.gob.ar"})
MAXIMO_QR = 2000  # caracteres del texto leído del QR
_AUTORIZACION_QR = {"E": "CAE", "A": "CAEA"}


class QRInvalido(ValueError):
    """El QR no es el de una factura electrónica de ARCA o trae datos que no cierran."""


@dataclass(frozen=True, slots=True)
class DatosQR:
    fecha: date
    cuit_emisor: str
    punto_venta: int
    tipo_comprobante: int
    numero: int
    importe_total: float
    moneda: str
    cotizacion: float
    tipo_doc_receptor: int | None
    nro_doc_receptor: str
    autorizacion: str  # CAE | CAEA
    codigo_autorizacion: str


def _entero(datos: dict, campo: str, minimo: int, maximo: int, obligatorio: bool = True) -> int | None:
    valor = datos.get(campo)
    if valor is None or valor == "":
        if obligatorio:
            raise QRInvalido(f"Al QR le falta el dato «{campo}».")
        return None
    # bool es un int en Python: no se acepta.
    if isinstance(valor, str) and valor.strip().isdigit():
        valor = int(valor.strip())
    if isinstance(valor, bool) or not isinstance(valor, int) or not minimo <= valor <= maximo:
        raise QRInvalido(f"El dato «{campo}» del QR no es válido.")
    return valor


def _decimal(datos: dict, campo: str, obligatorio: bool = True) -> float | None:
    valor = datos.get(campo)
    if valor is None or valor == "":
        if obligatorio:
            raise QRInvalido(f"Al QR le falta el dato «{campo}».")
        return None
    if isinstance(valor, str) and re.fullmatch(r"\d{1,13}(\.\d{1,6})?", valor.strip()):
        valor = float(valor.strip())
    if isinstance(valor, bool) or not isinstance(valor, int | float):
        raise QRInvalido(f"El dato «{campo}» del QR no es válido.")
    valor = float(valor)
    # La comparación encadenada también rechaza NaN e infinito.
    if not 0 < valor < 1e12:
        raise QRInvalido(f"El dato «{campo}» del QR no es válido.")
    return valor


def _base64(texto: str) -> bytes:
    """Base64 normal o con alfabeto de URL, con o sin el relleno final."""
    limpio = "".join(texto.split()).replace("-", "+").replace("_", "/").rstrip("=")
    if not limpio or len(limpio) % 4 == 1:
        raise QRInvalido("El QR no trae los datos de la factura.")
    try:
        return base64.b64decode(limpio + "=" * (-len(limpio) % 4), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise QRInvalido("El QR no trae los datos de la factura.") from exc


def leer_qr(texto: str) -> DatosQR:
    """Decodifica y valida el QR de una factura electrónica de ARCA."""
    texto = (texto or "").strip()
    if not texto or len(texto) > MAXIMO_QR or not texto.isascii():
        raise QRInvalido("Ese QR no es el de una factura electrónica de ARCA.")
    try:
        partes = urlsplit(texto)
        puerto = partes.port
    except ValueError as exc:
        raise QRInvalido("Ese QR no es el de una factura electrónica de ARCA.") from exc
    host = (partes.hostname or "").lower()
    if (partes.scheme.lower() != "https" or host not in HOSTS_QR or partes.username or partes.password
            or puerto not in (None, 443) or not partes.path.rstrip("/").lower().endswith("/fe/qr")):
        raise QRInvalido("Ese QR no es el de una factura electrónica de ARCA.")
    # La consulta se separa a mano: con parse_qs el «+» del base64 se convertiría en espacio.
    valores = [unquote(v) for k, _, v in (p.partition("=") for p in partes.query.split("&")) if k == "p"]
    if len(valores) != 1:
        raise QRInvalido("El QR no trae los datos de la factura.")
    try:
        datos = json.loads(_base64(valores[0]).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise QRInvalido("El QR no trae los datos de la factura.") from exc
    if not isinstance(datos, dict):
        raise QRInvalido("El QR no trae los datos de la factura.")
    if _entero(datos, "ver", 1, 99) != 1:
        raise QRInvalido("Esta versión del QR de ARCA no se conoce todavía.")
    texto_fecha = datos.get("fecha")
    if not isinstance(texto_fecha, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto_fecha):
        raise QRInvalido("La fecha del QR no es válida.")
    try:
        fecha = date.fromisoformat(texto_fecha)
    except ValueError as exc:
        raise QRInvalido("La fecha del QR no es válida.") from exc
    cuit = str(_entero(datos, "cuit", 20_000_000_000, 34_999_999_999))
    if not cuit_valido(cuit):
        raise QRInvalido("El CUIT del proveedor que trae el QR no es válido.")
    moneda = datos.get("moneda")
    if not isinstance(moneda, str) or not re.fullmatch(r"[A-Z0-9]{3}", moneda):
        raise QRInvalido("La moneda del QR no es válida.")
    cotizacion = _decimal(datos, "ctz", obligatorio=False)
    if moneda != "PES" and (cotizacion is None or not 0 < cotizacion < 1e7):
        # Sin cotización no se puede mostrar el equivalente en pesos: que se cargue a mano.
        raise QRInvalido("El QR de una factura en moneda extranjera no trae una cotización válida.")
    tipo_cod = datos.get("tipoCodAut")
    if tipo_cod not in _AUTORIZACION_QR:
        raise QRInvalido("El QR no dice si la factura tiene CAE o CAEA.")
    codigo = datos.get("codAut")
    if isinstance(codigo, bool) or not isinstance(codigo, int | str) or not re.fullmatch(r"\d{14}", str(codigo).strip()):
        raise QRInvalido("El código de autorización del QR tiene que tener 14 números.")
    nro_doc = _entero(datos, "nroDocRec", 0, 99_999_999_999, obligatorio=False)
    return DatosQR(
        fecha=fecha, cuit_emisor=cuit,
        punto_venta=_entero(datos, "ptoVta", 1, 99999),
        tipo_comprobante=_entero(datos, "tipoCmp", 1, 999),
        numero=_entero(datos, "nroCmp", 1, 99_999_999),
        importe_total=_decimal(datos, "importe"), moneda=moneda,
        cotizacion=1.0 if moneda == "PES" else cotizacion,
        tipo_doc_receptor=_entero(datos, "tipoDocRec", 0, 999, obligatorio=False),
        nro_doc_receptor="" if not nro_doc else str(nro_doc),
        autorizacion=_AUTORIZACION_QR[tipo_cod], codigo_autorizacion=str(codigo).strip(),
    )


# --- Foto -------------------------------------------------------------------

MAXIMO_FOTO = 2 * 1024 * 1024


def tipo_imagen(contenido: bytes) -> str | None:
    """Tipo de la imagen por sus primeros bytes (no por el nombre): jpeg, png o webp."""
    if contenido.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(contenido) >= 12 and contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp"
    return None


def validar_foto(contenido: bytes) -> str:
    if not contenido:
        raise ValueError("No llegó la foto: sacala de nuevo.")
    if len(contenido) > MAXIMO_FOTO:
        raise ValueError("La foto es muy grande: el máximo es 2 MB.")
    tipo = tipo_imagen(contenido)
    if tipo is None:
        raise ValueError("La foto tiene que ser JPG, PNG o WEBP.")
    return tipo


# --- Lectura sin QR ---------------------------------------------------------

_CUIT_TEXTO = re.compile(r"(?<!\d)(\d{2})[\s.-]?(\d{8})[\s.-]?(\d)(?!\d)")
_COMPROBANTE = re.compile(r"(?<!\d)(\d{4,5})\s*-\s*(\d{8})(?!\d)")
_PTO_NRO = re.compile(r"punto\s*de\s*venta\D{0,6}(\d{1,5})\D{0,40}?(?:comp|n[uú]mero|nro)\.?\D{0,8}(\d{1,8})",
                      re.IGNORECASE)
_FECHA = re.compile(r"(?<!\d)(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?!\d)")
_FECHA_EMISION = re.compile(r"fecha\s*(?:de\s*)?emisi[oó]n\D{0,6}(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", re.IGNORECASE)
_IMPORTE = re.compile(r"(?:importe\s*)?total\s*(?:\$|ars)?\s*:?\s*\$?\s*(\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})|\d+(?:[.,]\d{2}))",
                      re.IGNORECASE)
_CAE = re.compile(r"\b(CAEA|CAE|CAI)\b\D{0,12}(\d{14})(?!\d)", re.IGNORECASE)
_CODIGO_TIPO = re.compile(r"c[oó]d(?:igo)?\.?\s*(?:n[°º.]?\s*)?:?\s*(\d{1,3})(?!\d)", re.IGNORECASE)


def _importe(texto: str) -> float | None:
    texto = texto.replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        valor = float(texto)
    except ValueError:
        return None
    return valor if 0 < valor < 1e12 else None


def _dia(d: str, m: str, a: str, hoy: date) -> date | None:
    try:
        fecha = date(int(a), int(m), int(d))
    except ValueError:
        return None
    return fecha if date(2000, 1, 1) <= fecha <= hoy else None


def extraer_datos(texto: str, cuit_empresas: dict[str, str], hoy: date) -> dict[str, object]:
    """Propuesta de datos de la factura leída del texto de la foto. Lo que no se encuentra va en None.

    Nunca es definitiva: quien carga la factura la confirma o corrige mirando el papel.
    """
    limpio = " ".join((texto or "").split())
    propias = {c: e for e, c in cuit_empresas.items() if c}
    empresa = None
    cuit_emisor = None
    for m in _CUIT_TEXTO.finditer(limpio):
        cuit = "".join(m.groups())
        if not cuit_valido(cuit):
            continue
        if cuit in propias:
            empresa = empresa or propias[cuit]
        elif cuit_emisor is None:
            cuit_emisor = cuit
    punto_venta = numero = None
    if (m := _PTO_NRO.search(limpio)) or (m := _COMPROBANTE.search(limpio)):
        punto_venta, numero = int(m.group(1)), int(m.group(2))
    if not (punto_venta and 0 < punto_venta <= 99999 and numero and 0 < numero <= 99_999_999):
        punto_venta = numero = None
    fecha = None
    if m := _FECHA_EMISION.search(limpio):
        fecha = _dia(*m.groups(), hoy)
    if fecha is None:
        fecha = next((f for m in _FECHA.finditer(limpio) if (f := _dia(*m.groups(), hoy))), None)
    importes = [v for m in _IMPORTE.finditer(limpio) if (v := _importe(m.group(1)))]
    # La línea «Importe total» suele ser la última que dice total.
    importe = importes[-1] if importes else None
    autorizacion = codigo = None
    if m := _CAE.search(limpio):
        autorizacion, codigo = m.group(1).upper(), m.group(2)
    elif re.search(r"controlador\s*fiscal|\bP\.?V\.?\s*N[°º]", limpio, re.IGNORECASE):
        autorizacion, codigo = "CF", ""
    tipo = None
    if (m := _CODIGO_TIPO.search(limpio)) and int(m.group(1)) in TIPOS_COMPROBANTE:
        tipo = int(m.group(1))
    elif m := re.search(r"\bfactura\s+([ABCM])\b", limpio, re.IGNORECASE):
        tipo = {"A": 1, "B": 6, "C": 11, "M": 51}[m.group(1).upper()]
    return {
        "empresa": empresa, "cuit_emisor": cuit_emisor, "tipo_comprobante": tipo, "punto_venta": punto_venta,
        "numero": numero, "fecha": fecha, "importe_total": importe, "autorizacion": autorizacion,
        "codigo_autorizacion": codigo,
    }
