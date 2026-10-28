"""Transporte SMTP sin credenciales ni direcciones fijadas en código."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage


class CorreoComprasSMTP:
    def __init__(
        self,
        host: str,
        puerto: int,
        remitente: str,
        usuario: str | None = None,
        clave: str | None = None,
        usar_tls: bool = True,
    ) -> None:
        self._host = host
        self._puerto = puerto
        self._remitente = remitente
        self._usuario = usuario
        self._clave = clave
        self._usar_tls = usar_tls

    def enviar(self, destinatario: str, asunto: str, cuerpo: str, identificador: str) -> None:
        mensaje = EmailMessage()
        mensaje["From"] = self._remitente
        mensaje["To"] = destinatario
        mensaje["Subject"] = asunto
        mensaje["X-Juviar-Idempotency-Key"] = identificador
        mensaje.set_content(cuerpo)
        with smtplib.SMTP(self._host, self._puerto, timeout=15) as smtp:
            if self._usar_tls:
                smtp.starttls()
            if self._usuario:
                smtp.login(self._usuario, self._clave or "")
            smtp.send_message(mensaje)
