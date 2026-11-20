"""Normalización defensiva del payload Meta reenviado por Chattigo."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

_TELEFONO = re.compile(r"^\d{8,20}$")
_MEDIA = re.compile(r"^[A-Za-z0-9._-]{1,200}$")
_MAX_TEXTO = 1000
# Archivos que el bot acepta: los mismos que Selección lee de los CV del mail (PDF y fotos).
TIPOS_ARCHIVO = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
_NOMBRE_INVALIDO = re.compile(r"[^\w .()-]", re.UNICODE)


@dataclass(frozen=True)
class MensajeEntrante:
    wamid: str
    telefono: str
    tipo: str
    texto: str | None
    enviado_en: datetime | None
    media_id: str | None = None  # foto o documento que mandó: se baja después con este identificador
    media_nombre: str | None = None  # nombre del documento, como lo mandó
    media_tipo: str | None = None  # tipo declarado (sólo los de TIPOS_ARCHIVO)


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
    if tipo in {"image", "document"}:
        return (mensaje.get(tipo) or {}).get("caption") or None
    return None


def _media(mensaje: dict) -> tuple[str | None, str | None, str | None]:
    """Identificador, nombre y tipo de la foto o el documento. Un tipo que no está en la lista
    no se baja: queda sólo el texto que lo acompaña."""
    tipo_mensaje = mensaje.get("type")
    if tipo_mensaje not in {"image", "document"}:
        return None, None, None
    datos = mensaje.get(tipo_mensaje) or {}
    valor = str(datos.get("id") or "")
    mime = str(datos.get("mime_type") or ("image/jpeg" if tipo_mensaje == "image" else "")).split(";")[0]
    mime = mime.strip().lower()
    if not _MEDIA.fullmatch(valor) or mime not in TIPOS_ARCHIVO:
        return None, None, None
    nombre = None
    if tipo_mensaje == "document":
        limpio = _NOMBRE_INVALIDO.sub("", str(datos.get("filename") or "")).strip()[:120]
        nombre = limpio or None
    return valor, nombre, mime


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
                media_id, media_nombre, media_tipo = _media(mensaje)
                marca = mensaje.get("timestamp")
                salida.append(
                    MensajeEntrante(
                        wamid=str(wamid)[:200],
                        telefono=telefono,
                        tipo=str(mensaje.get("type") or "desconocido")[:30],
                        texto=texto[:_MAX_TEXTO] if isinstance(texto, str) else None,
                        media_id=media_id,
                        media_nombre=media_nombre,
                        media_tipo=media_tipo,
                        enviado_en=(
                            datetime.fromtimestamp(int(marca), UTC)
                            if str(marca or "").isdigit()
                            else None
                        ),
                    )
                )
    return salida
