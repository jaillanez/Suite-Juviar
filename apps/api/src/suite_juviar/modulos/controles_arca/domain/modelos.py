"""Controles fiscales de ARCA (ex AFIP) sobre cada factura de proveedor.

Pedido de Administración: por cada factura se hacen cinco controles y cada constancia
queda guardada en PDF.

1. Control impositivo (Reproweb, agente de retención y consulta puntual): se hace con
   clave fiscal en ARCA, no tiene servicio web. Queda pendiente hasta que alguien sube
   el PDF que bajó de ARCA.
2. Constancia de inscripción: servicio web ``ws_sr_constancia_inscripcion`` (padrón A5).
3. Facturas apócrifas: listado completo que publica ARCA, se cruza el CUIT.
4. Autorización del comprobante (CAE, CAI o CAEA): servicio web ``wscdc``. Las facturas
   de controlador fiscal no se controlan (configurable: la normativa cambia).
5. Agentes de retención (RG 18): listado completo que publica ARCA.

Los nombres de los PDF siguen la costumbre de Administración:
``CUIT_N_DD-MM-AAAA`` y, para el control de la factura, ``CUIT_4_NNNNNNNN_DD-MM-AAAA``.
"""

from __future__ import annotations

import re
from dataclasses import MISSING, dataclass, field, fields
from datetime import date, datetime, timedelta, timezone
from enum import IntEnum, StrEnum
from urllib.parse import urlsplit, urlunsplit

EMPRESAS = ("ENAV", "JUBIAR")
CUIT_REPRESENTANTE = "20172238832"
AMBIENTES = {"homologacion": "Homologación (pruebas de ARCA)", "produccion": "Producción"}
# Hora de Argentina (sin horario de verano) para fechar constancias y nombres de PDF.
HORA_ARGENTINA = timezone(timedelta(hours=-3), "ART")

# Hosts aceptados para bajar listados: sólo los sitios oficiales de ARCA.
_HOSTS_ARCA = (".afip.gob.ar", ".afip.gov.ar", ".arca.gob.ar")
_CUIT = re.compile(r"^\d{11}$")
_CODIGO = re.compile(r"^\d{14}$")
_MONEDA = re.compile(r"^[A-Z0-9]{3}$")
_PESOS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


class Control(IntEnum):
    IMPOSITIVO = 1
    INSCRIPCION = 2
    APOCRIFAS = 3
    COMPROBANTE = 4
    RG18 = 5


NOMBRES_CONTROL = {
    Control.IMPOSITIVO: "Control impositivo",
    Control.INSCRIPCION: "Constancia de inscripción",
    Control.APOCRIFAS: "Facturas apócrifas",
    Control.COMPROBANTE: "Autorización de la factura",
    Control.RG18: "Agentes de retención (RG 18)",
}
DESCRIPCION_CONTROL = {
    Control.IMPOSITIVO: "Reproweb, agente de retención y consulta puntual, con clave fiscal en ARCA.",
    Control.INSCRIPCION: "Que el proveedor esté inscripto y con la clave activa.",
    Control.APOCRIFAS: "Que el proveedor no figure en la base de facturas apócrifas.",
    Control.COMPROBANTE: "Que el CAE, CAI o CAEA de la factura sea válido para esos datos.",
    Control.RG18: "Si el proveedor figura como agente de retención.",
}
AUTOMATICOS = (Control.INSCRIPCION, Control.APOCRIFAS, Control.COMPROBANTE, Control.RG18)


class Estado(StrEnum):
    OK = "ok"
    ALERTA = "alerta"
    PENDIENTE = "pendiente"
    NO_APLICA = "no_aplica"
    SIN_CONFIGURAR = "sin_configurar"
    ERROR = "error"  # ARCA no respondió: se puede volver a probar


NOMBRES_ESTADO = {
    Estado.OK: "Bien", Estado.ALERTA: "Alerta", Estado.PENDIENTE: "Pendiente",
    Estado.NO_APLICA: "No corresponde", Estado.SIN_CONFIGURAR: "Falta configurar",
    Estado.ERROR: "No se pudo consultar",
}

AUTORIZACIONES = {
    "CAE": "CAE (factura electrónica)",
    "CAEA": "CAEA (anticipado)",
    "CAI": "CAI (factura impresa)",
    "CF": "Controlador fiscal",
}

TIPOS_COMPROBANTE = {
    1: "Factura A", 2: "Nota de débito A", 3: "Nota de crédito A",
    6: "Factura B", 7: "Nota de débito B", 8: "Nota de crédito B",
    11: "Factura C", 12: "Nota de débito C", 13: "Nota de crédito C",
    51: "Factura M", 52: "Nota de débito M", 53: "Nota de crédito M",
    81: "Tique factura A", 82: "Tique factura B", 83: "Tique",
    201: "Factura de crédito MiPyME A", 202: "Nota de débito MiPyME A", 203: "Nota de crédito MiPyME A",
    206: "Factura de crédito MiPyME B", 207: "Nota de débito MiPyME B", 208: "Nota de crédito MiPyME B",
    211: "Factura de crédito MiPyME C", 212: "Nota de débito MiPyME C", 213: "Nota de crédito MiPyME C",
}

# Códigos de moneda de ARCA (tabla de monedas de factura electrónica). El QR puede traer
# cualquier otro código de tres letras o números: se guarda tal cual.
MONEDAS = {"PES": "Pesos argentinos", "DOL": "Dólar estadounidense", "060": "Euro"}
# Cómo se muestra la moneda: la sigla que conoce todo el mundo; si no está, el código de ARCA.
SIGLAS_MONEDA = {"PES": "$", "DOL": "USD", "060": "EUR"}
PESOS = "PES"


def sigla_moneda(moneda: str) -> str:
    return SIGLAS_MONEDA.get(moneda, moneda)


def numero_ar(valor: float, decimales: int = 2) -> str:
    """1524.5 → «1.524,50»: separador de miles con punto y coma decimal, como se escribe acá."""
    return f"{valor:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def importe_escrito(importe: float, moneda: str = PESOS, cotizacion: float = 1.0) -> str:
    """«$ 12.100,50» en pesos; «USD 297,36 (≈ $ 453.325,32 a 1.524,50)» en moneda extranjera."""
    if moneda == PESOS:
        return f"$ {numero_ar(importe)}"
    # La cotización con los decimales que traiga (ARCA admite hasta seis), y al menos dos.
    decimales = max(2, len(f"{cotizacion:.6f}".rstrip("0").partition(".")[2]))
    return (f"{sigla_moneda(moneda)} {numero_ar(importe)} "
            f"(≈ $ {numero_ar(importe * cotizacion)} a {numero_ar(cotizacion, decimales)})")


URL_APOCRIFAS = "https://servicioscf.afip.gob.ar/Facturacion/facturasApocrifas/DownloadFile.aspx"
URL_RG18 = "https://servicioscf.afip.gob.ar/Publico/rg18/Archivos/RG18.csv"
ENLACES_IMPOSITIVO = (
    "https://auth.afip.gob.ar/contribuyente_/login.xhtml",
    "https://serviciospl.afip.gob.ar/pls/agr2/agr_inicio",
)


class ErrorARCA(Exception):
    """ARCA no respondió o rechazó la consulta; el mensaje se puede mostrar en pantalla."""


def cuit_valido(cuit: str) -> bool:
    """11 números y dígito verificador correcto (módulo 11)."""
    if not _CUIT.match(cuit or ""):
        return False
    resto = 11 - sum(int(d) * p for d, p in zip(cuit[:10], _PESOS, strict=True)) % 11
    verificador = {11: 0, 10: None}.get(resto, resto)
    return verificador is not None and verificador == int(cuit[10])


def validar_cuit(cuit: str, quien: str = "El CUIT") -> str:
    cuit = "".join((cuit or "").split()).replace("-", "")
    if not cuit_valido(cuit):
        raise ValueError(f"{quien} no es válido: tienen que ser 11 números y el último tiene que cerrar.")
    return cuit


def validar_url(url: str, que: str) -> str:
    """Sólo https a un dominio de ARCA, sin usuario ni clave en la dirección y sin otro puerto."""
    url = (url or "").strip()
    error = ValueError(f"La dirección de {que} tiene que ser de un sitio de ARCA y empezar con https://.")
    # Sólo caracteres comunes: nada de espacios, controles ni letras parecidas de otros alfabetos.
    if not url.isascii() or any(c.isspace() or ord(c) < 0x20 or ord(c) == 0x7F or c == "\\" for c in url):
        raise error
    try:
        partes = urlsplit(url)
        puerto = partes.port
    except ValueError:
        partes, puerto = None, -1
    host = (partes.hostname or "") if partes else ""
    if (len(url) > 300 or not partes or partes.scheme != "https" or partes.username or partes.password
            or puerto not in (None, 443) or not host.endswith(_HOSTS_ARCA)):
        raise error
    # Se devuelve armada de nuevo: lo que se usa es exactamente lo que se validó.
    return urlunsplit(("https", host, partes.path, partes.query, ""))


def nombre_pdf(cuit: str, control: int, fecha: date, numero_comprobante: int | None = None) -> str:
    """``CUIT_N_DD-MM-AAAA``; para el control de la factura ``CUIT_4_NNNNNNNN_DD-MM-AAAA``."""
    dia = fecha.strftime("%d-%m-%Y")
    if control == Control.COMPROBANTE:
        if numero_comprobante is None:
            raise ValueError("Falta el número de la factura para el nombre del PDF.")
        return f"{cuit}_{int(control)}_{numero_comprobante:08d}_{dia}"
    return f"{cuit}_{int(control)}_{dia}"


@dataclass(frozen=True, slots=True)
class Resultado:
    control: Control
    estado: Estado
    detalle: str
    fuente: str
    fecha: datetime
    actor: str
    archivo: str = ""  # nombre del PDF guardado, sin extensión; vacío si no hay
    nota: str = ""


@dataclass(frozen=True, slots=True)
class Factura:
    id: str
    empresa: str
    cuit_emisor: str
    razon_social: str
    tipo_comprobante: int
    punto_venta: int
    numero: int
    fecha: date
    importe_total: float
    autorizacion: str
    codigo_autorizacion: str
    cargada_por: str
    cargada_en: datetime
    resultados: tuple[Resultado, ...] = ()
    # Moneda del comprobante (código de ARCA) y cotización a pesos del día de la factura.
    # El importe total está en esa moneda: así lo constata ARCA.
    moneda: str = PESOS
    cotizacion: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.moneda, str) or not _MONEDA.match(self.moneda):
            raise ValueError("La moneda tiene que ser un código de ARCA de tres letras o números (PES, DOL, 060…).")
        if self.moneda == PESOS:
            object.__setattr__(self, "cotizacion", 1.0)
        elif isinstance(self.cotizacion, bool) or not isinstance(self.cotizacion, int | float) \
                or not 0 < self.cotizacion < 1e7:
            raise ValueError("La cotización tiene que ser más de cero.")
        else:
            object.__setattr__(self, "cotizacion", float(self.cotizacion))
        if self.empresa not in EMPRESAS:
            raise ValueError("Elegí a qué empresa se le facturó: ENAV o JUBIAR.")
        if not cuit_valido(self.cuit_emisor):
            raise ValueError("El CUIT del proveedor no es válido: tienen que ser 11 números y el último tiene que cerrar.")
        if len(self.razon_social) > 120:
            raise ValueError("La razón social es demasiado larga.")
        if self.tipo_comprobante not in TIPOS_COMPROBANTE:
            raise ValueError("Elegí el tipo de comprobante de la lista.")
        if not 0 < self.punto_venta <= 99999:
            raise ValueError("El punto de venta tiene que ser un número de 1 a 99999.")
        if not 0 < self.numero <= 99999999:
            raise ValueError("El número de factura tiene que ser de 1 a 99999999.")
        if not date(2000, 1, 1) <= self.fecha:
            raise ValueError("La fecha de la factura no es válida.")
        # La comparación encadenada también rechaza NaN e infinito.
        if not 0 < self.importe_total < 1e12:
            raise ValueError("El importe total tiene que ser más de cero.")
        if self.autorizacion not in AUTORIZACIONES:
            raise ValueError("Elegí cómo está autorizada la factura: CAE, CAEA, CAI o controlador fiscal.")
        if self.autorizacion == "CF":
            if self.codigo_autorizacion:
                raise ValueError("Las facturas de controlador fiscal no llevan código de autorización.")
        elif not _CODIGO.match(self.codigo_autorizacion):
            raise ValueError(f"El {self.autorizacion} tiene que tener 14 números.")

    # Las facturas se guardan con pickle. Las guardadas antes de agregar un campo traen menos
    # valores: el __setstate__ que arma dataclasses con slots dejaría ese campo sin asignar
    # (AttributeError al leerlo), así que los que faltan toman su valor por defecto.
    def __getstate__(self) -> list[object]:
        return [getattr(self, f.name) for f in fields(self)]

    def __setstate__(self, estado: list[object] | tuple[object, ...]) -> None:
        campos = fields(self)
        if len(estado) > len(campos):
            raise ValueError("La factura guardada tiene más datos de los que se conocen.")
        for campo, valor in zip(campos, estado, strict=False):
            object.__setattr__(self, campo.name, valor)
        for campo in campos[len(estado):]:
            if campo.default is MISSING:
                raise ValueError(f"A la factura guardada le falta «{campo.name}».")
            object.__setattr__(self, campo.name, campo.default)

    def resultado(self, control: Control) -> Resultado | None:
        return next((r for r in self.resultados if r.control == control), None)

    @property
    def importe_pesos(self) -> float:
        return round(self.importe_total * self.cotizacion, 2)

    @property
    def importe_texto(self) -> str:
        return importe_escrito(self.importe_total, self.moneda, self.cotizacion)

    @property
    def alerta(self) -> bool:
        return any(r.estado is Estado.ALERTA for r in self.resultados)

    @property
    def comprobante(self) -> str:
        return f"{TIPOS_COMPROBANTE[self.tipo_comprobante]} {self.punto_venta:05d}-{self.numero:08d}"


@dataclass(frozen=True, slots=True)
class Parametros:
    controles_activos: frozenset[int] = frozenset(int(c) for c in Control)
    # Normativa vigente: las facturas de controlador fiscal no se constatan.
    excluir_controlador_fiscal: bool = True
    ambiente: str = "homologacion"
    cuit_representante: str = CUIT_REPRESENTANTE
    cuit_empresas: dict[str, str] = field(default_factory=lambda: dict.fromkeys(EMPRESAS, ""))
    url_apocrifas: str = URL_APOCRIFAS
    url_rg18: str = URL_RG18
    enlaces_impositivo: tuple[str, ...] = ENLACES_IMPOSITIVO
    actualizado_por: str = ""
    actualizado_en: datetime | None = None

    def __post_init__(self) -> None:
        if not self.controles_activos <= {int(c) for c in Control}:
            raise ValueError("Hay un control que no existe.")
        if self.ambiente not in AMBIENTES:
            raise ValueError("El ambiente tiene que ser homologación o producción.")
        validar_cuit(self.cuit_representante, "El CUIT del representante")
        if set(self.cuit_empresas) != set(EMPRESAS):
            raise ValueError("Cargá el CUIT de ENAV y de JUBIAR (o dejalos vacíos).")
        for empresa, cuit in self.cuit_empresas.items():
            if cuit:
                validar_cuit(cuit, f"El CUIT de {empresa}")
        object.__setattr__(self, "url_apocrifas", validar_url(self.url_apocrifas, "facturas apócrifas"))
        object.__setattr__(self, "url_rg18", validar_url(self.url_rg18, "agentes de retención"))
        if not 1 <= len(self.enlaces_impositivo) <= 6:
            raise ValueError("Cargá entre 1 y 6 enlaces para el control impositivo.")
        object.__setattr__(self, "enlaces_impositivo",
                           type(self.enlaces_impositivo)(validar_url(e, "control impositivo") for e in self.enlaces_impositivo))


@dataclass(frozen=True, slots=True)
class Padron:
    """Listado completo bajado de ARCA. ``registros`` va de CUIT a sus filas."""

    nombre: str  # apocrifas | rg18
    url: str
    descargado_en: datetime
    generado: str  # fecha que trae el propio archivo
    registros: dict[str, tuple[tuple[str, ...], ...]]


@dataclass(frozen=True, slots=True)
class Constancia:
    """Lo que devuelve la constancia de inscripción (padrón A5)."""

    encontrada: bool
    razon_social: str = ""
    estado_clave: str = ""
    impuestos: tuple[str, ...] = ()
    monotributo: str = ""
    errores: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Constatacion:
    """Respuesta de la constatación de comprobantes (wscdc)."""

    resultado: str  # A aprobado | R rechazado
    observaciones: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AccesoARCA:
    """Certificado y clave para firmar el pedido de acceso. La clave vive sólo en memoria."""

    ambiente: str
    certificado_pem: str
    clave_pem: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class Credencial:
    """Clave privada (cifrada) generada en el servidor y, cuando llega, el certificado de ARCA."""

    cuit: str
    alias: str
    clave_cifrada: bytes = field(repr=False)
    csr_pem: str
    pedido_por: str
    pedido_en: datetime
    certificado_pem: str = ""
    sujeto: str = ""
    vence: datetime | None = None
    cargado_por: str = ""
    cargado_en: datetime | None = None


@dataclass(frozen=True, slots=True)
class DatosCertificado:
    cuit: str
    sujeto: str
    vence: datetime


# --- Reglas -------------------------------------------------------------------

def _fecha(texto: str) -> date | None:
    try:
        return datetime.strptime(texto.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def evaluar_apocrifa(padron: Padron, cuit: str) -> tuple[Estado, str]:
    filas = padron.registros.get(cuit)
    if not filas:
        return Estado.OK, "El proveedor no figura en la base de facturas apócrifas de ARCA."
    condicion, publicacion = filas[0][0], filas[0][1] if len(filas[0]) > 1 else ""
    return Estado.ALERTA, (f"El proveedor figura en la base de facturas apócrifas de ARCA "
                           f"(condición de apócrifo desde {condicion or 'sin fecha'}, publicado {publicacion or 'sin fecha'}).")


def evaluar_rg18(padron: Padron, cuit: str, el_dia: date) -> tuple[Estado, str]:
    """Es informativo: que el proveedor sea agente de retención no es un problema."""
    vigentes = []
    for fila in padron.registros.get(cuit, ()):
        desde, hasta = _fecha(fila[1]) if len(fila) > 1 else None, _fecha(fila[2]) if len(fila) > 2 else None
        if (desde is None or desde <= el_dia) and (hasta is None or el_dia <= hasta):
            vigentes.append(fila)
    if vigentes:
        fila = vigentes[0]
        inciso = fila[3] if len(fila) > 3 and fila[3] else "sin inciso"
        return Estado.OK, f"Es agente de retención (RG 18) desde {fila[1] or 'sin fecha'}, inciso {inciso}."
    if cuit in padron.registros:
        return Estado.OK, "Fue agente de retención (RG 18), pero no a la fecha de la factura."
    return Estado.OK, "No figura como agente de retención (RG 18)."


def evaluar_constancia(constancia: Constancia) -> tuple[Estado, str]:
    if not constancia.encontrada:
        return Estado.ALERTA, "ARCA no tiene registrado ese CUIT."
    nombre = f"{constancia.razon_social}: " if constancia.razon_social else ""
    if constancia.errores:
        return Estado.ALERTA, nombre + "ARCA no da la constancia: " + "; ".join(constancia.errores)[:400]
    if constancia.estado_clave and constancia.estado_clave.upper() != "ACTIVO":
        return Estado.ALERTA, nombre + f"La clave del proveedor está {constancia.estado_clave.lower()}."
    if constancia.monotributo:
        return Estado.OK, nombre + f"Inscripto en el monotributo ({constancia.monotributo})."
    if constancia.impuestos:
        return Estado.OK, nombre + "Inscripto en " + ", ".join(constancia.impuestos)[:400] + "."
    return Estado.ALERTA, nombre + "No tiene impuestos activos."


def evaluar_constatacion(constatacion: Constatacion, autorizacion: str) -> tuple[Estado, str]:
    obs = "; ".join(constatacion.observaciones)[:400]
    if constatacion.resultado.upper() == "A":
        return Estado.OK, f"ARCA confirma el {autorizacion} con los datos de la factura." + (f" ({obs})" if obs else "")
    return Estado.ALERTA, f"ARCA no confirma el {autorizacion}: " + (obs or "los datos no coinciden.")
