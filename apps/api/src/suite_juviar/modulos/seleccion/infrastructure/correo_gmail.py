"""Casilla Gmail de RRHH leída por IMAP con una contraseña de aplicación de Google.

Sólo lee: abre la bandeja en modo de lectura, no marca correos como leídos ni
los mueve. Cada adjunto se identifica por el Message-ID del correo y el nombre
del archivo, así un mismo envío nunca entra dos veces.
"""

from __future__ import annotations

import email
import imaplib
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import PurePath

from ..domain.modelos import DocumentoEntrante, OrigenCV

SERVIDOR_GMAIL = "imap.gmail.com"
EXTENSIONES_CV = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
TAMANO_MAXIMO = 15 * 1024 * 1024
_MESES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class ErrorCorreo(RuntimeError):
    """Falla de conexión o de acceso, con un mensaje que RRHH puede entender."""


def _texto(valor: str | None) -> str:
    return str(make_header(decode_header(valor))) if valor else ""


def _fecha_imap(dia: date) -> str:
    return f"{dia.day:02d}-{_MESES[dia.month - 1]}-{dia.year}"


def _recibido_en(mensaje: Message) -> datetime:
    try:
        fecha = parsedate_to_datetime(mensaje["Date"])
    except (TypeError, ValueError):
        return datetime.now(UTC)
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=UTC)


class BandejaGmailIMAP:
    estado = "GMAIL_IMAP_CONTRASENA_DE_APLICACION"

    def __init__(
        self,
        casilla: str,
        clave_aplicacion: str,
        desde: date,
        conectar: Callable[[str], imaplib.IMAP4] = lambda servidor: imaplib.IMAP4_SSL(servidor, timeout=60),
    ) -> None:
        self._casilla = casilla.strip().lower()
        # Google muestra la contraseña de aplicación en grupos de cuatro letras.
        self._clave = clave_aplicacion.replace(" ", "")
        self._desde = desde
        self._conectar = conectar

    def _abrir(self) -> imaplib.IMAP4:
        try:
            conexion = self._conectar(SERVIDOR_GMAIL)
        except OSError as exc:
            raise ErrorCorreo("No se pudo conectar con Gmail. Revisá la conexión a internet del servidor.") from exc
        try:
            conexion.login(self._casilla, self._clave)
        except imaplib.IMAP4.error as exc:
            raise ErrorCorreo(
                "Gmail rechazó la casilla o la contraseña de aplicación. "
                "Verificá que la contraseña sea de aplicación y no la clave común de Gmail."
            ) from exc
        estado, _ = conexion.select("INBOX", readonly=True)
        if estado != "OK":
            raise ErrorCorreo("No se pudo abrir la bandeja de entrada.")
        return conexion

    def probar(self) -> None:
        conexion = self._abrir()
        conexion.logout()

    def listar_nuevos(self) -> list[DocumentoEntrante]:
        conexion = self._abrir()
        try:
            estado, datos = conexion.search(None, f"(SINCE {_fecha_imap(self._desde)})")
            if estado != "OK":
                raise ErrorCorreo("Gmail no respondió la búsqueda de correos.")
            documentos: list[DocumentoEntrante] = []
            for numero in (datos[0] or b"").split():
                estado, partes = conexion.fetch(numero, "(BODY.PEEK[])")
                if estado != "OK":
                    continue
                crudo = next((p[1] for p in partes if isinstance(p, tuple)), None)
                if crudo:
                    documentos.extend(self._adjuntos(email.message_from_bytes(crudo)))
            return documentos
        finally:
            conexion.logout()

    def _adjuntos(self, mensaje: Message) -> list[DocumentoEntrante]:
        identificador = (mensaje["Message-ID"] or "").strip() or f"sin-id:{mensaje['Date']}:{mensaje['From']}"
        recibido = _recibido_en(mensaje)
        encontrados = []
        for parte in mensaje.walk():
            nombre = _texto(parte.get_filename())
            if not nombre or PurePath(nombre).suffix.lower() not in EXTENSIONES_CV:
                continue
            contenido = parte.get_payload(decode=True)
            if not contenido or len(contenido) > TAMANO_MAXIMO:
                continue
            encontrados.append(DocumentoEntrante(
                origen=OrigenCV.CORREO,
                referencia_fuente=f"gmail:{self._casilla}:{identificador}:{nombre}",
                nombre_archivo=nombre,
                contenido=contenido,
                recibido_en=recibido,
                fuente_simulada=False,
            ))
        return encontrados


def desde_para(ultima_lectura: datetime | None, dias_iniciales: int = 30) -> date:
    """La primera vez trae el último mes; después, desde un día antes de la última lectura."""
    if ultima_lectura is None:
        return (datetime.now(UTC) - timedelta(days=dias_iniciales)).date()
    return (ultima_lectura - timedelta(days=1)).date()
