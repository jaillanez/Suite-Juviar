"""Ingreso con correo y contraseña, y administración de usuarios de Gestión."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from ..application.ingreso import DURACION_SESION
from ..domain.usuarios import DatosDeUsuarioInvalidos, IngresoInvalido, Usuario
from .dependencias import (
    COOKIE_SESION,
    SesionActual,
    exigir_permiso,
    identidad_es_simulada,
    servicio_ingreso,
)

Token = Annotated[str | None, Cookie(alias=COOKIE_SESION)]


class IngresoEntrada(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    clave: str = Field(min_length=1, max_length=200)
    empresa: str | None = None


class CambioClaveEntrada(BaseModel):
    actual: str = Field(min_length=1, max_length=200)
    nueva: str = Field(min_length=1, max_length=200)


class EmpresaEntrada(BaseModel):
    empresa: str


class UsuarioEntrada(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    nombre: str = Field(min_length=1, max_length=120)
    perfil: str
    empresas: list[str] = Field(min_length=1, max_length=2)
    clave_inicial: str = Field(min_length=1, max_length=200)


class UsuarioCambios(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    perfil: str
    empresas: list[str] = Field(min_length=1, max_length=2)
    activo: bool


class ClaveTemporalEntrada(BaseModel):
    clave_temporal: str = Field(min_length=1, max_length=200)


def _publico(usuario: Usuario) -> dict[str, object]:
    return {
        "id": usuario.id, "email": usuario.email, "nombre": usuario.nombre,
        "perfil": usuario.perfil, "empresas": list(usuario.empresas), "activo": usuario.activo,
        "debe_cambiar_clave": usuario.debe_cambiar_clave,
        "creado_en": usuario.creado_en.isoformat(),
    }


def _poner_cookie(respuesta: Response, token: str) -> None:
    respuesta.set_cookie(
        COOKIE_SESION, token, max_age=int(DURACION_SESION.total_seconds()), httponly=True,
        secure=os.getenv("SJ_COOKIE_SEGURA", "1").strip() != "0", samesite="strict", path="/",
    )


def _datos_invalidos(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


router = APIRouter(prefix="/ingreso", tags=["ingreso"])


@router.get("/estado")
def estado() -> dict[str, bool]:
    return {"identidad_real": not identidad_es_simulada()}


@router.post("")
def ingresar(entrada: IngresoEntrada, respuesta: Response, request: Request):
    origen = request.client.host if request.client else ""
    try:
        token, _ = servicio_ingreso().ingresar(
            entrada.email, entrada.clave, entrada.empresa, origen=origen
        )
    except IngresoInvalido as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    _poner_cookie(respuesta, token)
    return yo(token)


@router.get("/yo")
def yo(token: Token = None):
    resuelto = servicio_ingreso().resolver(token) if token else None
    if resuelto is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta una sesión autenticada.")
    usuario, sesion = resuelto
    return {**_publico(usuario), "empresa_sesion": sesion.empresa}


@router.post("/salir")
def salir(respuesta: Response, token: Token = None):
    if token:
        servicio_ingreso().salir(token)
    respuesta.delete_cookie(COOKIE_SESION, path="/")
    return {"ok": True}


@router.post("/clave")
def cambiar_clave(entrada: CambioClaveEntrada, token: Token = None):
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta una sesión autenticada.")
    try:
        servicio_ingreso().cambiar_clave_propia(token, entrada.actual, entrada.nueva)
    except IngresoInvalido as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    except DatosDeUsuarioInvalidos as exc:
        raise _datos_invalidos(exc) from exc
    return yo(token)


@router.put("/empresa")
def cambiar_empresa(entrada: EmpresaEntrada, sesion: SesionActual, token: Token = None):
    del sesion  # exige una sesión válida y con la contraseña ya cambiada
    try:
        servicio_ingreso().cambiar_empresa(token or "", entrada.empresa)
    except IngresoInvalido as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    except DatosDeUsuarioInvalidos as exc:
        raise _datos_invalidos(exc) from exc
    return yo(token)


usuarios = APIRouter(
    prefix="/usuarios",
    tags=["usuarios"],
    dependencies=[Depends(exigir_permiso("identidad.usuarios.gestionar"))],
)


@usuarios.get("")
def listar_usuarios():
    return [_publico(u) for u in servicio_ingreso().repositorio.listar()]


@usuarios.post("")
def crear_usuario(entrada: UsuarioEntrada, sesion: SesionActual):
    try:
        usuario = servicio_ingreso().crear_usuario(
            sesion.actor, entrada.email, entrada.nombre, entrada.perfil, entrada.empresas,
            entrada.clave_inicial,
        )
    except DatosDeUsuarioInvalidos as exc:
        raise _datos_invalidos(exc) from exc
    return _publico(usuario)


@usuarios.put("/{usuario_id}")
def modificar_usuario(usuario_id: str, entrada: UsuarioCambios, sesion: SesionActual):
    try:
        usuario = servicio_ingreso().modificar_usuario(
            sesion.actor, usuario_id, nombre=entrada.nombre, perfil=entrada.perfil,
            empresas=entrada.empresas, activo=entrada.activo,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except DatosDeUsuarioInvalidos as exc:
        raise _datos_invalidos(exc) from exc
    return _publico(usuario)


@usuarios.post("/{usuario_id}/clave")
def restablecer_clave(usuario_id: str, entrada: ClaveTemporalEntrada, sesion: SesionActual):
    try:
        servicio_ingreso().restablecer_clave(sesion.actor, usuario_id, entrada.clave_temporal)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except DatosDeUsuarioInvalidos as exc:
        raise _datos_invalidos(exc) from exc
    return {"ok": True}


@usuarios.get("/accesos")
def accesos():
    return servicio_ingreso().repositorio.eventos()
