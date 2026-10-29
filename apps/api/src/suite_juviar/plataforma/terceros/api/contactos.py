from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import SesionActual, exigir_permiso
from suite_juviar.plataforma.terceros.application.contactos import GestionarContactos
from suite_juviar.plataforma.terceros.telefono import TelefonoInvalido
from suite_juviar.plataforma.terceros.telefono import normalizar as normalizar_telefono

from . import tablero_fila

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


def _exigir_que_no_sea_personal(telefono: str) -> None:
    """Un celular es de productor o de empleado, nunca de los dos (infra/034).

    La base DMZ lo vuelve a controlar al publicar; acá se avisa en el momento de cargarlo.
    """
    try:
        normalizado = normalizar_telefono(telefono)
    except TelefonoInvalido as exc:
        raise HTTPException(422, str(exc)) from exc
    if not tablero_fila._dsn:
        return
    if tablero_fila._leer(
        "SELECT 1 FROM consulta.telefono_personal WHERE telefono = %(t)s AND activo",
        {"t": normalizado},
    ):
        raise HTTPException(409, "Ese celular ya está cargado como personal de la empresa.")


class CambioTareas(BaseModel):
    tareas: set[str]


class Alta(BaseModel):
    telefono: str
    tareas: set[str]
    motivo: str = Field(min_length=3, max_length=240)


class Baja(BaseModel):
    motivo: str = Field(min_length=3, max_length=240)


class Reemplazo(BaseModel):
    anterior: str = Field(pattern=r"^[0-9]{8,20}$")
    nuevo: str = Field(pattern=r"^[0-9]{8,20}$")
    motivo: str = Field(min_length=3, max_length=240)


class Descartar(BaseModel):
    nota: str = Field(min_length=3, max_length=500)


@router.post("/{clientecuit}", status_code=201)
def alta(
    clientecuit: str,
    datos: Alta,
    sesion: SesionActual,
    _: Autorizado,
    gestor: Servicio,
):
    _exigir_que_no_sea_personal(datos.telefono)
    try:
        gestor.alta(clientecuit, datos.telefono, datos.tareas, sesion.actor, datos.motivo)
    except TelefonoInvalido as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/pendientes/lista")
def pendientes(_: Autorizado, gestor: Servicio):
    return gestor.pendientes()


@router.get("/productores/lista")
def productores(_: Autorizado, gestor: Servicio):
    return gestor.productores()


@router.get("/productores/buscar")
def buscar_productores(q: str, _: Autorizado, gestor: Servicio):
    return gestor.buscar_productores(q)


@router.post("/pendientes/{pendiente_id}/resolver", status_code=204)
def resolver_pendiente(
    pendiente_id: int,
    clientecuit: str,
    datos: Alta,
    sesion: SesionActual,
    _: Autorizado,
    gestor: Servicio,
):
    _exigir_que_no_sea_personal(datos.telefono)
    try:
        gestor.repo.resolver_pendiente(
            pendiente_id,
            clientecuit,
            datos.tareas,
            sesion.actor,
            datos.motivo,
        )
    except (TelefonoInvalido, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/pendientes/{pendiente_id}/descartar", status_code=204)
def descartar_pendiente(
    pendiente_id: int,
    datos: Descartar,
    sesion: SesionActual,
    _: Autorizado,
    gestor: Servicio,
):
    try:
        gestor.descartar_pendiente(pendiente_id, sesion.actor, datos.nota)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


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
    _exigir_que_no_sea_personal(datos.nuevo)
    try:
        gestor.reemplazar(clientecuit, datos.anterior, datos.nuevo, sesion.actor, datos.motivo)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
