"""Canales del aviso de mosto virgen demorado y el ciclo que los revisa."""

from __future__ import annotations

import logging
import smtplib
import threading
from email.message import EmailMessage

import psycopg

from ..application.servicios import GestionarMosto

_registro = logging.getLogger(__name__)


class CorreoSMTP:
    canal = "correo"

    def __init__(self, host: str, puerto: int, remitente: str, usuario: str | None, clave: str | None,
                 usar_tls: bool = True) -> None:
        self._host, self._puerto, self._remitente = host, puerto, remitente
        self._usuario, self._clave, self._usar_tls = usuario, clave, usar_tls

    def enviar(self, destino: str, asunto: str, texto: str) -> str:
        if not self._host or not self._remitente:
            return "sin_configurar"
        mensaje = EmailMessage()
        mensaje["From"], mensaje["To"], mensaje["Subject"] = self._remitente, destino, asunto
        mensaje.set_content(texto)
        with smtplib.SMTP(self._host, self._puerto, timeout=15) as smtp:
            if self._usar_tls:
                smtp.starttls()
            if self._usuario:
                smtp.login(self._usuario, self._clave or "")
            smtp.send_message(mensaje)
        return "enviado"


class WhatsappPorBot:
    """Deja el mensaje en la cola del bot (infra/040); lo manda el worker por Chattigo."""

    canal = "whatsapp"

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def enviar(self, destino: str, asunto: str, texto: str) -> str:
        if not self._dsn:
            return "sin_configurar"
        with psycopg.connect(self._dsn, connect_timeout=5) as cn:
            cn.execute("SELECT fila.encolar_aviso_interno(%s, %s)", (destino, texto))
        return "encolado"


def iniciar(servicio: GestionarMosto, cada_segundos: int = 60) -> threading.Thread:
    def ciclo() -> None:
        while True:
            threading.Event().wait(cada_segundos)
            try:
                for aviso in servicio.revisar_demoras():
                    _registro.warning("Mosto virgen demorado: %s", aviso.texto)
            except Exception:  # noqa: BLE001 - el ciclo no se corta por un error puntual
                _registro.exception("No se pudieron revisar los viajes de mosto virgen.")

    hilo = threading.Thread(target=ciclo, name="alarma-mosto-virgen", daemon=True)
    hilo.start()
    return hilo
