"""Clientes SOAP de ARCA: WSAA (acceso), padrón A5 (constancia de inscripción) y WSCDC.

Sin zeep: el XML se arma a mano y se lee con ElementTree. El pedido de acceso (TRA) se
firma en CMS/PKCS#7 con el certificado del representante; el permiso que devuelve WSAA
(token y firma) dura unas 12 horas y se guarda cifrado, porque ARCA no entrega otro
mientras el anterior siga vigente.
"""

from __future__ import annotations

import base64
import hashlib
import json
import ssl
import xml.etree.ElementTree as ET
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from xml.sax.saxutils import escape

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7

from ..domain.modelos import (
    HORA_ARGENTINA,
    AccesoARCA,
    Constancia,
    Constatacion,
    ErrorARCA,
    Factura,
)
from ..domain.puertos import Cifrador

ENDPOINTS = {
    "homologacion": {
        "wsaa": "https://wsaahomo.afip.gov.ar/ws/services/LoginCms",
        "padron": "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA5",
        "wscdc": "https://wswhomo.afip.gov.ar/WSCDC/service.asmx",
    },
    "produccion": {
        "wsaa": "https://wsaa.afip.gov.ar/ws/services/LoginCms",
        "padron": "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA5",
        "wscdc": "https://servicios1.afip.gov.ar/WSCDC/service.asmx",
    },
}
SERVICIO_PADRON = "ws_sr_constancia_inscripcion"
SERVICIO_CDC = "wscdc"
_NS_CDC = "http://servicios1.afip.gob.ar/wscdc/"
_SOBRE = ('<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope '
          'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" {ns}><soapenv:Header/>'
          '<soapenv:Body>{cuerpo}</soapenv:Body></soapenv:Envelope>')


# Servidores de ARCA que todavía usan claves DH cortas: sólo con ellos se acepta ese cifrado.
HOSTS_CIFRADO_VIEJO = frozenset({"servicios1.afip.gov.ar"})


def cliente_http(cifrado_viejo: bool = False) -> httpx.Client:
    """TLS con el certificado del servidor verificado. ``cifrado_viejo`` baja el nivel de cifrado
    aceptado (SECLEVEL=1) y se usa sólo para los servidores de ``HOSTS_CIFRADO_VIEJO``."""
    contexto = ssl.create_default_context()
    if cifrado_viejo:
        contexto.set_ciphers("DEFAULT@SECLEVEL=1")
    return httpx.Client(verify=contexto, timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=False)


@dataclass(frozen=True, slots=True)
class Ticket:
    token: str
    sign: str
    vence: datetime


def _local(elemento: ET.Element) -> str:
    return elemento.tag.rsplit("}", 1)[-1]


def _buscar(raiz: ET.Element | None, nombre: str) -> ET.Element | None:
    if raiz is None:
        return None
    return next((e for e in raiz.iter() if _local(e) == nombre), None)


def _todos(raiz: ET.Element | None, nombre: str) -> list[ET.Element]:
    return [] if raiz is None else [e for e in raiz.iter() if _local(e) == nombre]


def _texto(raiz: ET.Element | None, nombre: str) -> str:
    elemento = _buscar(raiz, nombre)
    return (elemento.text or "").strip() if elemento is not None else ""


def _hijos(raiz: ET.Element | None, nombre: str) -> list[ET.Element]:
    return [] if raiz is None else [e for e in raiz if _local(e) == nombre]


def _texto_hijo(raiz: ET.Element | None, nombre: str) -> str:
    hijos = _hijos(raiz, nombre)
    return (hijos[0].text or "").strip() if hijos else ""


def armar_tra(servicio: str, ahora: datetime) -> str:
    """Pedido de acceso (loginTicketRequest) válido por diez minutos."""
    local = ahora.astimezone(HORA_ARGENTINA).replace(microsecond=0)
    return ('<?xml version="1.0" encoding="UTF-8"?><loginTicketRequest version="1.0"><header>'
            f"<uniqueId>{int(ahora.timestamp())}</uniqueId>"
            f"<generationTime>{(local - timedelta(minutes=10)).isoformat()}</generationTime>"
            f"<expirationTime>{(local + timedelta(minutes=10)).isoformat()}</expirationTime>"
            f"</header><service>{escape(servicio)}</service></loginTicketRequest>")


def firmar_tra(tra: str, certificado_pem: str, clave_pem: str) -> str:
    """CMS (PKCS#7) firmado, con el TRA adentro, en base64."""
    certificado = x509.load_pem_x509_certificate(certificado_pem.encode())
    clave = serialization.load_pem_private_key(clave_pem.encode(), password=None)
    firmado = (pkcs7.PKCS7SignatureBuilder().set_data(tra.encode())
               .add_signer(certificado, clave, hashes.SHA256())  # type: ignore[arg-type]
               .sign(serialization.Encoding.DER, []))
    return base64.b64encode(firmado).decode()


def _leer_xml(contenido: bytes, servicio: str) -> ET.Element:
    # ElementTree no resuelve entidades externas; además se rechaza cualquier DOCTYPE
    # (las respuestas de ARCA nunca lo traen) para cortar entidades anidadas.
    if b"<!DOCTYPE" in contenido.upper() or b"<!ENTITY" in contenido.upper():
        raise ErrorARCA(f"ARCA ({servicio}) respondió algo que no se puede leer.")
    try:
        return ET.fromstring(contenido)
    except ET.ParseError as exc:
        raise ErrorARCA(f"ARCA ({servicio}) respondió algo que no se puede leer.") from exc


def _falla(raiz: ET.Element) -> str:
    falla = _buscar(raiz, "Fault")
    return _texto(falla, "faultstring") if falla is not None else ""


def leer_ticket(contenido: bytes) -> Ticket:
    raiz = _leer_xml(contenido, "acceso")
    if falla := _falla(raiz):
        if "alreadyAuthenticated" in falla or "TA valido" in falla:
            raise ErrorARCA("ARCA ya dio un permiso vigente a este certificado y Gestión no lo tiene: "
                            "hay que esperar a que venza (hasta 12 horas) y volver a probar.")
        raise ErrorARCA(f"ARCA no dio acceso: {falla[:200]}")
    retorno = _texto(raiz, "loginCmsReturn")
    if not retorno:
        raise ErrorARCA("ARCA no devolvió el permiso de acceso.")
    respuesta = _leer_xml(retorno.encode(), "acceso")
    token, sign, vence = _texto(respuesta, "token"), _texto(respuesta, "sign"), _texto(respuesta, "expirationTime")
    if not token or not sign or not vence:
        raise ErrorARCA("El permiso de acceso de ARCA vino incompleto.")
    return Ticket(token, sign, datetime.fromisoformat(vence))


class ConectorARCAWeb:
    """Implementa el puerto ``ConectorARCA`` contra los servicios web reales."""

    def __init__(self, tickets: MutableMapping[str, bytes], cifrador: Cifrador,
                 http: httpx.Client | None = None, reloj: Callable[[], datetime] = lambda: datetime.now(UTC),
                 endpoints: dict[str, dict[str, str]] | None = None) -> None:
        self._tickets = tickets
        self._cifrador = cifrador
        self._http = http or cliente_http()
        self._http_viejo = http or cliente_http(cifrado_viejo=True)
        self._reloj = reloj
        self._endpoints = endpoints or ENDPOINTS
        self._bloqueo = RLock()

    def _post(self, url: str, cuerpo: str, accion: str = "") -> bytes:
        try:
            http = self._http_viejo if httpx.URL(url).host in HOSTS_CIFRADO_VIEJO else self._http
            respuesta = http.post(url, content=cuerpo.encode(), headers={
                "Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{accion}"'})
        except httpx.HTTPError as exc:
            raise ErrorARCA("No hubo conexión con ARCA. Probá de nuevo más tarde.") from exc
        # Las fallas SOAP vienen con 500 y el detalle en el cuerpo.
        if respuesta.status_code >= 400 and b"Fault" not in respuesta.content:
            raise ErrorARCA(f"ARCA respondió con error {respuesta.status_code}. Probá de nuevo más tarde.")
        return respuesta.content

    def ticket(self, acceso: AccesoARCA, servicio: str) -> Ticket:
        huella = hashlib.sha256(acceso.certificado_pem.encode()).hexdigest()[:16]
        clave = f"{acceso.ambiente}:{servicio}:{huella}"
        with self._bloqueo:
            guardado = self._tickets.get(clave)
            if guardado is not None:
                datos = json.loads(self._cifrador.descifrar(guardado))
                ticket = Ticket(datos["token"], datos["sign"], datetime.fromisoformat(datos["vence"]))
                if ticket.vence - timedelta(minutes=5) > self._reloj():
                    return ticket
            cms = firmar_tra(armar_tra(servicio, self._reloj()), acceso.certificado_pem, acceso.clave_pem)
            cuerpo = _SOBRE.format(ns='xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov"',
                                   cuerpo=f"<wsaa:loginCms><wsaa:in0>{cms}</wsaa:in0></wsaa:loginCms>")
            ticket = leer_ticket(self._post(self._endpoints[acceso.ambiente]["wsaa"], cuerpo))
            self._tickets[clave] = self._cifrador.cifrar(json.dumps(
                {"token": ticket.token, "sign": ticket.sign, "vence": ticket.vence.isoformat()}))
            return ticket

    def constancia(self, acceso: AccesoARCA, cuit_representada: str, cuit: str) -> Constancia:
        ticket = self.ticket(acceso, SERVICIO_PADRON)
        cuerpo = _SOBRE.format(ns='xmlns:a5="http://a5.soap.ws.server.puc.sr/"', cuerpo=(
            f"<a5:getPersona_v2><token>{escape(ticket.token)}</token><sign>{escape(ticket.sign)}</sign>"
            f"<cuitRepresentada>{int(cuit_representada)}</cuitRepresentada>"
            f"<idPersona>{int(cuit)}</idPersona></a5:getPersona_v2>"))
        return leer_constancia(self._post(self._endpoints[acceso.ambiente]["padron"], cuerpo))

    def constatar(self, acceso: AccesoARCA, cuit_representada: str, factura: Factura,
                  cuit_receptor: str) -> Constatacion:
        ticket = self.ticket(acceso, SERVICIO_CDC)
        cuerpo = _SOBRE.format(ns="", cuerpo=(
            f'<ComprobanteConstatar xmlns="{_NS_CDC}"><Auth><Token>{escape(ticket.token)}</Token>'
            f"<Sign>{escape(ticket.sign)}</Sign><Cuit>{int(cuit_representada)}</Cuit></Auth><CmpReq>"
            f"<CbteModo>{escape(factura.autorizacion)}</CbteModo><CuitEmisor>{int(factura.cuit_emisor)}</CuitEmisor>"
            f"<PtoVta>{factura.punto_venta}</PtoVta><CbteTipo>{factura.tipo_comprobante}</CbteTipo>"
            f"<CbteNro>{factura.numero}</CbteNro><CbteFch>{factura.fecha:%Y%m%d}</CbteFch>"
            f"<ImpTotal>{factura.importe_total:.2f}</ImpTotal>"
            f"<CodAutorizacion>{escape(factura.codigo_autorizacion)}</CodAutorizacion>"
            f"<DocTipoReceptor>80</DocTipoReceptor><DocNroReceptor>{int(cuit_receptor)}</DocNroReceptor>"
            "</CmpReq></ComprobanteConstatar>"))
        return leer_constatacion(self._post(self._endpoints[acceso.ambiente]["wscdc"], cuerpo,
                                            f"{_NS_CDC}ComprobanteConstatar"))


def leer_constancia(contenido: bytes) -> Constancia:
    raiz = _leer_xml(contenido, "constancia de inscripción")
    if falla := _falla(raiz):
        if "no existe" in falla.lower():
            return Constancia(encontrada=False)
        raise ErrorARCA(f"ARCA no dio la constancia: {falla[:200]}")
    persona = _buscar(raiz, "personaReturn")
    if persona is None:
        raise ErrorARCA("ARCA no devolvió la constancia de inscripción.")
    generales = _buscar(persona, "datosGenerales")
    razon = _texto_hijo(generales, "razonSocial") or " ".join(
        t for t in (_texto_hijo(generales, "apellido"), _texto_hijo(generales, "nombre")) if t)
    regimen = _buscar(persona, "datosRegimenGeneral")
    impuestos = tuple(t for i in _hijos(regimen, "impuesto") if (t := _texto_hijo(i, "descripcionImpuesto")))
    mono = _buscar(persona, "datosMonotributo")
    monotributo = ""
    if mono is not None:
        monotributo = _texto(_buscar(mono, "categoriaMonotributo"), "descripcionCategoria") or "monotributo"
    errores = tuple((e.text or "").strip() for e in _hijos(_buscar(persona, "errorConstancia"), "error")
                    if (e.text or "").strip())
    return Constancia(True, razon, _texto_hijo(generales, "estadoClave"), impuestos, monotributo, errores)


def leer_constatacion(contenido: bytes) -> Constatacion:
    raiz = _leer_xml(contenido, "constatación de comprobantes")
    if falla := _falla(raiz):
        raise ErrorARCA(f"ARCA no constató la factura: {falla[:200]}")
    resultado = _buscar(raiz, "ComprobanteConstatarResult")
    if resultado is None:
        raise ErrorARCA("ARCA no devolvió la constatación de la factura.")
    observaciones = tuple(f"{_texto(o, 'Msg')} (código {_texto(o, 'Code')})" for o in _todos(resultado, "Obs"))
    estado = _texto_hijo(resultado, "Resultado")
    if not estado:
        errores = "; ".join(f"{_texto(e, 'Msg')} (código {_texto(e, 'Code')})" for e in _todos(resultado, "Err"))
        raise ErrorARCA(f"ARCA respondió con error: {errores[:200] or 'sin detalle'}")
    return Constatacion(estado, observaciones)
