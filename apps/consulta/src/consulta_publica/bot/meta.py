"""Normalización defensiva del payload Meta reenviado por Chattigo."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

_TELEFONO = re.compile(r"^\d{8,20}$")
_MEDIA = re.compile(r"^[A-Za-z0-9._-]{1,200}$")
_MAX_TEXTO = 1000


@dataclass(frozen=True)
class MensajeEntrante:
    wamid: str
    telefono: str
    tipo: str
    texto: str | None
    enviado_en: datetime | None
    media_id: str | None = None  # foto que mandó: se baja después con este identificador


def _texto(mensaje: dict) -> str | None:
    tipo = mensaje.get("type")
    if tipo == "text":
        return (mensaje.get("text") or {}).get("body")
    if tipo == "button":
        return (mensaje.get("button") or {}).get("text")
    if tipo == "interactive":
        interactivo = mensaje.get("interactive") or {}
        respuesta = interactivo.get("button_reply") or interactivo.get("list_reply") or {}
        return respuesta.get("title")
    if tipo == "image":
        return (mensaje.get("image") or {}).get("caption") or None
    return None


def _media_id(mensaje: dict) -> str | None:
    if mensaje.get("type") != "image":
        return None
    valor = str((mensaje.get("image") or {}).get("id") or "")
    return valor if _MEDIA.fullmatch(valor) else None


def extraer_mensajes(payload: object, numero_id: str | None = None) -> list[MensajeEntrante]:
    """Con numero_id, sólo los mensajes que llegaron a ese número (una app de Meta puede
    tener varios números: los de otro sistema no entran al bot)."""
    if not isinstance(payload, dict):
        return []
    salida: list[MensajeEntrante] = []
    for entrada in payload.get("entry") or []:
        for cambio in (entrada or {}).get("changes") or []:
            valor = (cambio or {}).get("value") or {}
            if numero_id is not None and str(
                    (valor.get("metadata") or {}).get("phone_number_id") or "") != numero_id:
                continue
            for mensaje in valor.get("messages") or []:
                if not isinstance(mensaje, dict):
                    continue
                wamid = mensaje.get("id")
                telefono = str(mensaje.get("from") or "")
                if not wamid or not _TELEFONO.fullmatch(telefono):
                    continue
                texto = _texto(mensaje)
                marca = mensaje.get("timestamp")
                salida.append(
                    MensajeEntrante(
                        wamid=str(wamid)[:200],
                        telefono=telefono,
                        tipo=str(mensaje.get("type") or "desconocido")[:30],
                        texto=texto[:_MAX_TEXTO] if isinstance(texto, str) else None,
                        media_id=_media_id(mensaje),
                        enviado_en=(
                            datetime.fromtimestamp(int(marca), UTC)
                            if str(marca or "").isdigit()
                            else None
                        ),
                    )
                )
    return salida
