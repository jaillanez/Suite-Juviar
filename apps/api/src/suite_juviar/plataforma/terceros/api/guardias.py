"""Tablets de guardia: los usuarios de la consola del portón de cada bodega.

Gestión las administra en la base DMZ con las funciones de infra/035 (rol gestion_tablero):
alta, cambio de nombre o sede, clave nueva, baja y reactivación. Nunca se borra un usuario
ni se leen los hashes de las claves. La clave temporal se muestra una sola vez.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import SesionActual, exigir_permiso

from .tablero_fila import _escribir, _leer

router = APIRouter(prefix="/guardias", tags=["guardias"])
Autorizado = Annotated[object, Depends(exigir_permiso("fila.contactos.gestionar"))]
Usuario = Annotated[str, Path(pattern=r"^[a-z0-9._-]{3,30}$")]


class DatosGuardia(BaseModel):
    nombre: str = Field(min_length=3, max_length=120)
    sede: str = Field(pattern=r"^[a-z0-9_-]{2,30}$")


class AltaGuardia(DatosGuardia):
    usuario: str = Field(pattern=r"^[a-z0-9._-]{3,30}$")


def _hash(clave: str) -> str:
    sal = secrets.token_bytes(16)
    derivada = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal, 600_000)
    return f"pbkdf2_sha256$600000${sal.hex()}${derivada.hex()}"


@router.get("")
def listar(_: Autorizado):
    return _leer(
        """SELECT usuario, nombre, sede, activo, debe_cambiar_clave, creado_por, creado_en, ultimo_ingreso
             FROM fila.guardia ORDER BY activo DESC, sede, nombre""",
        {},
    )


@router.get("/{usuario}/historial")
def historial(usuario: Usuario, _: Autorizado):
    return _leer(
        """SELECT tipo, actor, detalle, momento FROM fila.guardia_evento
            WHERE usuario = %(usuario)s ORDER BY momento DESC LIMIT 50""",
        {"usuario": usuario},
    )


@router.post("", status_code=201)
def crear(datos: AltaGuardia, sesion: SesionActual, _: Autorizado):
    clave = secrets.token_urlsafe(8)
    _escribir(
        "SELECT fila.crear_guardia(%(usuario)s, %(nombre)s, %(sede)s, %(hash)s, %(actor)s)",
        {"usuario": datos.usuario, "nombre": datos.nombre, "sede": datos.sede,
         "hash": _hash(clave), "actor": sesion.actor},
    )
    return {"usuario": datos.usuario, "clave_temporal": clave}


@router.put("/{usuario}", status_code=204)
def modificar(usuario: Usuario, datos: DatosGuardia, sesion: SesionActual, _: Autorizado):
    _escribir(
        "SELECT fila.modificar_guardia(%(usuario)s, %(nombre)s, %(sede)s, %(actor)s)",
        {"usuario": usuario, "nombre": datos.nombre, "sede": datos.sede, "actor": sesion.actor},
    )


@router.post("/{usuario}/clave")
def nueva_clave(usuario: Usuario, sesion: SesionActual, _: Autorizado):
    """Clave temporal nueva. También reactiva una tablet deshabilitada."""
    clave = secrets.token_urlsafe(8)
    _escribir(
        "SELECT fila.nueva_clave_guardia(%(usuario)s, %(hash)s, %(actor)s)",
        {"usuario": usuario, "hash": _hash(clave), "actor": sesion.actor},
    )
    return {"usuario": usuario, "clave_temporal": clave}


@router.post("/{usuario}/baja", status_code=204)
def baja(usuario: Usuario, sesion: SesionActual, _: Autorizado):
    _escribir("SELECT fila.baja_guardia(%(usuario)s, %(actor)s)", {"usuario": usuario, "actor": sesion.actor})
