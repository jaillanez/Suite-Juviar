"""Ingreso a la pantalla /subir con el link personal y el PIN de 3 dígitos.

La sesión queda en una cookie propia (HttpOnly, Secure, SameSite=Strict) por 30 días y
sólo tiene el permiso de subir facturas desde el celular. La administración de las
personas está en Controles ARCA (permiso ``parametros.gestionar``).
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from ..domain.subida_pin import DURACION_SESION_SUBIDA, IngresoSubidaInvalido, PersonaSubida
from .dependencias import COOKIE_SUBIDA, servicio_subida

TokenSubida = Annotated[str | None, Cookie(alias=COOKIE_SUBIDA)]

_ESTADO_HTTP = {
    "link": status.HTTP_401_UNAUTHORIZED,
    "pin": status.HTTP_401_UNAUTHORIZED,
    "bloqueado": status.HTTP_429_TOO_MANY_REQUESTS,
    "demasiados": status.HTTP_429_TOO_MANY_REQUESTS,
    "desactivado": status.HTTP_403_FORBIDDEN,
}


class IngresoSubidaEntrada(BaseModel):
    codigo: str = Field(min_length=1, max_length=120)
    pin: str = Field(pattern=r"^[0-9]{3}$")


def _publico(persona: PersonaSubida) -> dict[str, object]:
    return {"nombre": persona.nombre, "empresas": list(persona.empresas)}


router = APIRouter(prefix="/subir", tags=["subir facturas con PIN"])


@router.post("/ingreso")
def ingresar(entrada: IngresoSubidaEntrada, respuesta: Response, request: Request):
    origen = request.client.host if request.client else ""
    try:
        token, persona = servicio_subida().ingresar(entrada.codigo, entrada.pin, origen=origen)
    except IngresoSubidaInvalido as exc:
        raise HTTPException(_ESTADO_HTTP.get(exc.motivo, 401), str(exc)) from exc
    respuesta.set_cookie(
        COOKIE_SUBIDA, token, max_age=int(DURACION_SESION_SUBIDA.total_seconds()), httponly=True,
        secure=os.getenv("SJ_COOKIE_SEGURA", "1").strip() != "0", samesite="strict", path="/",
    )
    return _publico(persona)


@router.get("/yo")
def yo(token: TokenSubida = None):
    persona = servicio_subida().resolver(token) if token else None
    if persona is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta ingresar con el PIN.")
    return _publico(persona)


@router.post("/salir")
def salir(respuesta: Response, token: TokenSubida = None):
    if token:
        servicio_subida().salir(token)
    respuesta.delete_cookie(COOKIE_SUBIDA, path="/")
    return {"ok": True}
