"""Simulador del bot de WhatsApp dentro de Gestión.

Manda al webhook del bot el mismo mensaje que mandaría WhatsApp y lee las respuestas que el
bot guarda en modo simulado (consulta.bot_salida_simulada). Sólo funciona si el servidor lo
habilita (SJ_SIMULADOR_BOT_HABILITADO=si), que se pone únicamente con el bot en modo
simulado: así nunca dispara mensajes reales a productores. Nunca en producción.

Sólo se puede escribir como los teléfonos de prueba de SJ_SIMULADOR_TELEFONOS: nadie puede
hacerse pasar por un productor real para ver sus entregas o anotarle turnos.
"""

from __future__ import annotations

import os
import time
from typing import Annotated
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import exigir_permiso

from .tablero_fila import _leer

router = APIRouter(prefix="/simulador-bot", tags=["simulador del bot"])
Autorizado = Annotated[object, Depends(exigir_permiso("bot.simulador.usar"))]


class Envio(BaseModel):
    telefono: str = Field(pattern=r"^\d{8,20}$")
    texto: str = Field(min_length=1, max_length=1000)


def _habilitado() -> str:
    url = os.getenv("SJ_BOT_WEBHOOK_URL", "").strip()
    entorno = (os.getenv("SJ_ENTORNO") or "").strip().lower()
    if (os.getenv("SJ_SIMULADOR_BOT_HABILITADO", "").strip().lower() not in {"1", "si", "true"}
            or not url or entorno in {"produccion", "production", "prod"}):
        raise HTTPException(503, "El simulador del bot no está habilitado en este servidor.")
    return url


def telefonos_de_prueba() -> list[str]:
    valor = os.getenv("SJ_SIMULADOR_TELEFONOS", "")
    return [t.strip() for t in valor.split(",") if t.strip().isdigit() and 8 <= len(t.strip()) <= 20]


def _exigir_de_prueba(telefono: str) -> None:
    if telefono not in telefonos_de_prueba():
        raise HTTPException(400, "Ese teléfono no es de prueba: el simulador sólo usa los teléfonos de prueba.")


def payload_meta(telefono: str, texto: str, wamid: str, marca: int) -> dict:
    """El mismo formato que manda WhatsApp (y que usaba apps/simulador)."""
    return {"object": "whatsapp_business_account", "entry": [{"id": "simulador", "changes": [{
        "field": "messages",
        "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "simulador", "phone_number_id": "simulador"},
            "contacts": [{"profile": {"name": "Simulador"}, "wa_id": telefono}],
            "messages": [{"from": telefono, "id": wamid, "timestamp": str(marca), "type": "text",
                          "text": {"body": texto}}],
        },
    }]}]}


@router.get("/estado")
def estado(_: Autorizado):
    try:
        _habilitado()
    except HTTPException:
        return {"habilitado": False}
    return {"habilitado": True}


@router.get("/telefonos")
def telefonos(_: Autorizado):
    _habilitado()
    return [{"telefono": t} for t in telefonos_de_prueba()]


@router.post("/enviar")
def enviar(envio: Envio, _: Autorizado):
    url = _habilitado()
    _exigir_de_prueba(envio.telefono)
    wamid = f"sim.in.{uuid4().hex}"
    try:
        respuesta = httpx.post(url, json=payload_meta(envio.telefono, envio.texto, wamid, int(time.time())),
                               timeout=10)
    except httpx.HTTPError as exc:
        raise HTTPException(502, "El bot no respondió. ¿Está encendido?") from exc
    if respuesta.status_code != 200:
        raise HTTPException(502, f"El bot rechazó el mensaje ({respuesta.status_code}).")
    return {"wamid": wamid}


@router.get("/respuestas")
def respuestas(_: Autorizado, telefono: str = Query(pattern=r"^\d{8,20}$"),
               desde_id: int = Query(0, ge=0)):
    _habilitado()
    _exigir_de_prueba(telefono)
    return _leer(
        """SELECT id, texto, creado_en FROM consulta.bot_salida_simulada
            WHERE telefono = %(telefono)s AND id > %(desde)s ORDER BY id LIMIT 50""",
        {"telefono": telefono, "desde": desde_id},
    )
