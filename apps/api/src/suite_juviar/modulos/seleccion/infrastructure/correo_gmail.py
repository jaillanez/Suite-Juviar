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
    except Exception:  # noqa: BLE001 - encabezado mal codificado: se usa tal como llegó
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
        cursor: dict[str, int] | None = None,
        conectar: Callable[[str], imaplib.IMAP4] = lambda servidor: imaplib.IMAP4_SSL(servidor, timeout=60),
    ) -> None:
        self._casilla = casilla.strip().lower()
        # Google muestra la contraseña de aplicación en grupos de cuatro letras.
        self._clave = clave_aplicacion.replace(" ", "")
        self._desde = desde
        self._conectar = conectar
        # Dónde quedó la lectura: el UID que Gmail asigna a cada correo. Crece siempre y no
        # depende de la fecha que escribe quien envía, así no se saltean ni se repiten correos.
        self.cursor = dict(cursor) if cursor else None
        self.completa = True
        self.salteados = 0

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
            validez = int((conexion.response("UIDVALIDITY")[1] or [b"0"])[0] or 0)
            anterior = self.cursor["uid"] if self.cursor and self.cursor.get("uidvalidity") == validez else None
            # Si Gmail renumeró la bandeja (cambia UIDVALIDITY) se vuelve a buscar por fecha;
            # los duplicados igual se descartan al incorporar.
            criterio = f"(UID {anterior + 1}:*)" if anterior is not None else f"(SINCE {_fecha_imap(self._desde)})"
            estado, datos = conexion.uid("SEARCH", None, criterio)
            if estado != "OK":
                raise ErrorCorreo("Gmail no respondió la búsqueda de correos.")
            # «UID n:*» siempre devuelve el último correo aunque sea viejo: se filtra.
            uids = sorted(u for u in map(int, (datos[0] or b"").split()) if anterior is None or u > anterior)
            self.completa = len(uids) <= MAXIMO_CORREOS_POR_LECTURA
            ultimo = anterior
            documentos: list[DocumentoEntrante] = []
            for uid in uids[:MAXIMO_CORREOS_POR_LECTURA]:
                if self._tamano(conexion, uid) <= TAMANO_MAXIMO_CORREO:
                    estado, partes = conexion.uid("FETCH", str(uid), "(BODY.PEEK[])")
                    if estado != "OK":
                        # Corte transitorio: se reintenta desde este correo en la próxima lectura.
                        self.completa = False
                        break
                    crudo = next((p[1] for p in partes or [] if isinstance(p, tuple)), None)
                    if not crudo:
                        # Gmail respondió sin contenido: se saltea para no quedar trabado en este correo.
                        self.salteados += 1
                        _registro.warning("Se salteó el correo UID %s de %s: llegó vacío.", uid, self._casilla)
                        ultimo = uid
                        continue
                    try:
                        documentos.extend(self._adjuntos(email.message_from_bytes(crudo)))
                    except Exception:  # noqa: BLE001
                        # Un correo mal armado no frena al resto ni se reintenta para siempre.
                        self.salteados += 1
                        _registro.warning("Se salteó el correo UID %s de %s: no se pudo leer.", uid, self._casilla)
                else:
                    self.salteados += 1
                ultimo = uid
            if ultimo is not None:
                self.cursor = {"uidvalidity": validez, "uid": ultimo}
            return documentos
        finally:
            conexion.logout()

    @staticmethod
    def _tamano(conexion: imaplib.IMAP4, uid: int) -> int:
        estado, partes = conexion.uid("FETCH", str(uid), "(RFC822.SIZE)")
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
