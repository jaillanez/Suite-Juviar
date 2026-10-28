from __future__ import annotations

import hashlib
import secrets
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import SesionActual, exigir_permiso

router = APIRouter(prefix="/guardias", tags=["guardias"])
_dsn = ""


def configurar(dsn: str) -> None:
    global _dsn
    _dsn = dsn


Autorizado = Annotated[object, Depends(exigir_permiso("fila.contactos.gestionar"))]


class AltaGuardia(BaseModel):
    usuario: str = Field(pattern=r"^[a-z0-9._-]{3,30}$")
    nombre: str = Field(min_length=3, max_length=120)
    sede: str = Field(pattern=r"^[a-z0-9_-]{2,30}$")


def _hash(clave: str) -> str:
    sal = secrets.token_bytes(16)
    derivada = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal, 600_000)
    return f"pbkdf2_sha256$600000${sal.hex()}${derivada.hex()}"


def _conexion():
    if not _dsn:
        raise HTTPException(503, "administración de guardias no configurada")
    return psycopg.connect(_dsn, row_factory=dict_row)


@router.get("")
def listar(_: Autorizado):
    with _conexion() as cn:
        filas = cn.execute(
            """SELECT usuario,nombre,sede,activo,debe_cambiar_clave,creado_en,ultimo_ingreso
               FROM fila.guardia ORDER BY activo DESC,sede,nombre"""
        ).fetchall()
    return [dict(f) for f in filas]


@router.post("", status_code=201)
def crear(datos: AltaGuardia, sesion: SesionActual, _: Autorizado):
    clave = secrets.token_urlsafe(8)
    try:
        with _conexion() as cn:
            cn.execute(
                """INSERT INTO fila.guardia
                   (usuario,nombre,sede,clave_hash,creado_por,debe_cambiar_clave)
                   VALUES (%s,%s,%s,%s,%s,true)""",
                (datos.usuario, datos.nombre, datos.sede, _hash(clave), sesion.actor),
            )
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, "el usuario ya existe") from exc
    return {"usuario": datos.usuario, "clave_temporal": clave}


@router.delete("/{usuario}", status_code=204)
def baja(usuario: str, _: Autorizado):
    with _conexion() as cn:
        fila = cn.execute(
            "UPDATE fila.guardia SET activo=false WHERE usuario=%s AND activo RETURNING usuario",
            (usuario,),
        ).fetchone()
        if not fila:
            raise HTTPException(404, "guardia activo inexistente")
        cn.execute(
            "UPDATE fila.sesion_guardia SET cerrada_en=now() WHERE usuario=%s AND cerrada_en IS NULL",
            (usuario,),
        )
