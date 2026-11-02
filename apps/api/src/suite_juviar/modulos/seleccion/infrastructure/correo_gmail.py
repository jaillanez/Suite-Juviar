"""Casilla Gmail de RRHH leída por IMAP con una contraseña de aplicación de Google.

Sólo lee: abre la bandeja en modo de lectura, no marca correos como leídos ni
los mueve. Cada adjunto se identifica por el Message-ID del correo y el nombre
del archivo, así un mismo envío nunca entra dos veces.
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
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
TAMANO_MAXIMO_CORREO = 25 * 1024 * 1024  # el límite de Gmail para un correo recibido
MAXIMO_CORREOS_POR_LECTURA = 500
_registro = logging.getLogger(__name__)
_MESES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class ErrorCorreo(RuntimeError):
    """Falla de conexión o de acceso, con un mensaje que RRHH puede entender."""


def _texto(valor: str | None) -> str:
    if not valor:
        return ""
    try:
        return str(make_header(decode_header(valor)))
    except Exception:  # encabezado mal codificado: se usa tal como llegó
        return str(valor)


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
        # Si hubo más correos que el tope, la próxima lectura sigue desde el último procesado.
        self.completa = True
        self.leido_hasta: datetime | None = None

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
            numeros = (datos[0] or b"").split()
            self.completa = len(numeros) <= MAXIMO_CORREOS_POR_LECTURA
            for numero in numeros[:MAXIMO_CORREOS_POR_LECTURA]:
                if self._tamano(conexion, numero) > TAMANO_MAXIMO_CORREO:
                    continue
                estado, partes = conexion.fetch(numero, "(BODY.PEEK[])")
                if estado != "OK":
                    continue
                crudo = next((p[1] for p in partes if isinstance(p, tuple)), None)
                if not crudo:
                    continue
                try:
                    mensaje = email.message_from_bytes(crudo)
                    self.leido_hasta = max(filter(None, (self.leido_hasta, _recibido_en(mensaje))))
                    documentos.extend(self._adjuntos(mensaje))
                except Exception:
                    # Un correo mal armado no frena la lectura del resto.
                    _registro.warning("Se salteó un correo de %s que no se pudo leer.", self._casilla)
            return documentos
        finally:
            conexion.logout()

    @staticmethod
    def _tamano(conexion: imaplib.IMAP4, numero: bytes) -> int:
        estado, partes = conexion.fetch(numero, "(RFC822.SIZE)")
        if estado != "OK" or not partes:
            return 0
        linea = partes[0] if isinstance(partes[0], bytes) else partes[0][0]
        coincidencia = re.search(rb"RFC822\.SIZE (\d+)", linea or b"")
        return int(coincidencia.group(1)) if coincidencia else 0

    def _adjuntos(self, mensaje: Message) -> list[DocumentoEntrante]:
        identificador = (mensaje["Message-ID"] or "").strip() or f"sin-id:{mensaje['Date']}:{mensaje['From']}"
        recibido = _recibido_en(mensaje)
        encontrados = []
        for parte in mensaje.walk():
            nombre = _texto(parte.get_filename())
            if not nombre or PurePath(nombre).suffix.lower() not in EXTENSIONES_CV:
                continue
            # El tamaño codificado se revisa antes de decodificar, para no armar archivos enormes.
            if len(str(parte.get_payload())) > TAMANO_MAXIMO * 4 // 3 + 4096:
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
