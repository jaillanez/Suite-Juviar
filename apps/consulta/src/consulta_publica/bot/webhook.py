"""Webhooks de WhatsApp (Chattigo y Meta directo): autentican, encolan y responden de inmediato."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from functools import lru_cache
from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
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
    return await _encolar(await _cuerpo(request), cola)


async def _cuerpo(request: Request) -> bytes:
    cuerpo = await request.body()
    if len(cuerpo) > TAMANO_MAXIMO:
        raise HTTPException(status_code=413)
    return cuerpo


async def _encolar(cuerpo: bytes, cola: Cola, numero_id: str | None = None) -> dict[str, int]:
    try:
        payload = json.loads(cuerpo)
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(status_code=400) from None
    mensajes = extraer_mensajes(payload, numero_id)
    nuevos = 0
    for mensaje in mensajes:
        nuevos += int(await run_in_threadpool(cola.encolar, mensaje))
    return {"recibidos": len(mensajes), "nuevos": nuevos}


# --- Meta directo -------------------------------------------------------------
# Meta verifica la dirección una vez con un GET (devolver el «challenge» si el
# token coincide) y firma cada aviso con la clave secreta de la app
# (X-Hub-Signature-256). Sin esas dos variables cargadas la dirección no existe.

def _meta(nombre: str) -> str:
    valor = os.environ.get(nombre, "").strip()
    if len(valor) < 16:
        raise HTTPException(status_code=404)
    return valor


@router.get("/webhook/meta", response_class=PlainTextResponse)
async def verificar_meta(
    modo: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    desafio: str = Query("", alias="hub.challenge", max_length=200),
) -> str:
    esperado = _meta("META_TOKEN_VERIFICACION")
    if modo != "subscribe" or not hmac.compare_digest(token.encode(), esperado.encode()):
        raise HTTPException(status_code=403)
    return desafio


@router.post("/webhook/meta")
async def recibir_meta(
    request: Request, cola: Cola = Depends(obtener_cola)  # noqa: B008
) -> dict[str, int]:
    clave = _meta("META_CLAVE_APP")
    numero_id = os.environ.get("META_NUMERO_ID", "").strip()
    if not numero_id:
        raise HTTPException(status_code=404)
    cuerpo = await _cuerpo(request)
    firma = request.headers.get("x-hub-signature-256", "")
    esperada = "sha256=" + hmac.new(clave.encode(), cuerpo, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(firma.encode(), esperada.encode()):
        raise HTTPException(status_code=403)
    return await _encolar(cuerpo, cola, numero_id)
