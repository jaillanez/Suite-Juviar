"""Webhook de Chattigo: autentica por URL, encola y responde de inmediato."""

from __future__ import annotations

import hmac
import json
import os
from functools import lru_cache
from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from .meta import MensajeEntrante, extraer_mensajes

LONGITUD_MINIMA_SECRETO = 48
TAMANO_MAXIMO = 256 * 1024


def cargar_secreto() -> str:
    secreto = os.environ.get("BOT_WEBHOOK_SECRETO", "")
    if len(secreto) < LONGITUD_MINIMA_SECRETO:
        raise RuntimeError(
            f"BOT_WEBHOOK_SECRETO ausente o menor a {LONGITUD_MINIMA_SECRETO} caracteres"
        )
    return secreto


@lru_cache(maxsize=1)
def _secreto() -> str:
    return cargar_secreto()


class Cola(Protocol):
    def encolar(self, mensaje: MensajeEntrante) -> bool: ...


def obtener_cola() -> Cola:
    raise RuntimeError("cola no configurada")


router = APIRouter()


@router.post("/webhook/chattigo/{secreto}")
async def recibir(
    secreto: str, request: Request, cola: Cola = Depends(obtener_cola)  # noqa: B008
) -> dict[str, int]:
    esperado = _secreto()
    if not secreto or not hmac.compare_digest(secreto.encode(), esperado.encode()):
        raise HTTPException(status_code=404)
    cuerpo = await request.body()
    if len(cuerpo) > TAMANO_MAXIMO:
        raise HTTPException(status_code=413)
    try:
        payload = json.loads(cuerpo)
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(status_code=400) from None
    mensajes = extraer_mensajes(payload)
    nuevos = 0
    for mensaje in mensajes:
        nuevos += int(await run_in_threadpool(cola.encolar, mensaje))
    return {"recibidos": len(mensajes), "nuevos": nuevos}
