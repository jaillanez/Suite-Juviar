"""Normalización defensiva del payload Meta reenviado por Chattigo."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

_TELEFONO = re.compile(r"^\d{8,20}$")
_MAX_TEXTO = 1000


@dataclass(frozen=True)
class MensajeEntrante:
    wamid: str
    telefono: str
    tipo: str
    texto: str | None
    enviado_en: datetime | None


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
    return None


def extraer_mensajes(payload: object) -> list[MensajeEntrante]:
    if not isinstance(payload, dict):
        return []
    salida: list[MensajeEntrante] = []
    for entrada in payload.get("entry") or []:
        for cambio in (entrada or {}).get("changes") or []:
            valor = (cambio or {}).get("value") or {}
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
                        enviado_en=(
                            datetime.fromtimestamp(int(marca), timezone.utc)
                            if str(marca or "").isdigit()
                            else None
                        ),
                    )
                )
    return salida
