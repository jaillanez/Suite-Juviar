from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import SesionActual, exigir_permiso
from suite_juviar.plataforma.terceros.application.contactos import GestionarContactos

router = APIRouter(prefix="/contactos", tags=["contactos"])
_servicio: GestionarContactos | None = None


def configurar(servicio: GestionarContactos) -> None:
    global _servicio
    _servicio = servicio


def servicio() -> GestionarContactos:
    if _servicio is None:
        raise HTTPException(503, "gestión de contactos no configurada")
    return _servicio


Servicio = Annotated[GestionarContactos, Depends(servicio)]
Autorizado = Annotated[object, Depends(exigir_permiso("fila.contactos.gestionar"))]


class CambioTareas(BaseModel):
    tareas: set[str]


class Baja(BaseModel):
    motivo: str = Field(min_length=3, max_length=240)


class Reemplazo(BaseModel):
    anterior: str = Field(pattern=r"^[0-9]{8,20}$")
    nuevo: str = Field(pattern=r"^[0-9]{8,20}$")
    motivo: str = Field(min_length=3, max_length=240)


@router.get("/{clientecuit}")
def listar(clientecuit: str, _: Autorizado, gestor: Servicio):
    return gestor.listar(clientecuit)


@router.put("/{clientecuit}/{telefono}/tareas", status_code=204)
def tareas(
    clientecuit: str,
    telefono: str,
    cambio: CambioTareas,
    sesion: SesionActual,
    _: Autorizado,
    gestor: Servicio,
):
    try:
        gestor.tareas(clientecuit, telefono, cambio.tareas, sesion.actor)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{clientecuit}/{telefono}/baja", status_code=204)
def baja(
    clientecuit: str,
    telefono: str,
    datos: Baja,
    sesion: SesionActual,
    _: Autorizado,
    gestor: Servicio,
):
    try:
        gestor.dar_baja(clientecuit, telefono, sesion.actor, datos.motivo)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{clientecuit}/reemplazar", status_code=204)
def reemplazar(
    clientecuit: str,
    datos: Reemplazo,
    sesion: SesionActual,
    _: Autorizado,
    gestor: Servicio,
):
    try:
        gestor.reemplazar(clientecuit, datos.anterior, datos.nuevo, sesion.actor, datos.motivo)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
