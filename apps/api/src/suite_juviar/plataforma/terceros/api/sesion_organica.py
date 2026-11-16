"""Sesión de uva orgánica de cada bodega (infra/039).

Mientras está abierta no entra uva convencional; la orgánica que entra sin sesión se
recibe como convencional. Todo es configurable por bodega: si recibe orgánica, quién abre
y cierra la sesión (guardia, báscula o ambos), si las franjas horarias son fijas por día o
se abren en el momento, y los días de prioridad de la orgánica al empezar la cosecha.

Bodega configura (fila.turnos.gestionar); Báscula abre y cierra (fila.organica.operar).
"""

from __future__ import annotations

from datetime import date, time
from typing import Annotated, Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, model_validator

from suite_juviar.plataforma.identidad.api.dependencias import exigir_permiso
from suite_juviar.plataforma.identidad.domain.sesion import Sesion

from . import tablero_fila
from .tablero_fila import NOMBRES, GestionaTurnos, _escribir, _leer, _sede_valida, sedes

router = APIRouter(prefix="/fila-organica", tags=["fila"])
Lee = Annotated[Sesion, Depends(exigir_permiso("fila.tablero.leer"))]
Opera = Annotated[Sesion, Depends(exigir_permiso("fila.organica.operar"))]
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


class Franja(BaseModel):
    dia: int = Field(ge=1, le=7)  # 1 lunes … 7 domingo
    desde: time
    hasta: time

    @model_validator(mode="after")
    def _orden(self) -> Franja:
        if self.desde >= self.hasta:
            raise ValueError("cada franja tiene que empezar antes de terminar")
        return self


class Parametros(BaseModel):
    recibe_organica: bool
    quien_abre: Literal["guardia", "bascula", "ambos"]
    modo_franjas: Literal["manual", "fijas"]
    inicio_cosecha: date | None = None
    dias_prioridad: int = Field(ge=0, le=120)
    franjas: list[Franja] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _sin_superponer(self) -> Parametros:
        for i, a in enumerate(self.franjas):
            for b in self.franjas[i + 1:]:
                if a.dia == b.dia and a.desde < b.hasta and b.desde < a.hasta:
                    raise ValueError(f"hay franjas que se superponen el {DIAS[a.dia - 1]}")
        return self


def _por_defecto(sede: str) -> dict:
    return {"sede": sede, "recibe_organica": False, "quien_abre": "ambos", "modo_franjas": "manual",
            "inicio_cosecha": None, "dias_prioridad": 15, "actualizado_por": None, "actualizado_en": None}


@router.get("")
def configuracion(_: Lee):
    lista = sedes()
    parametros = {p["sede"]: p for p in _leer(
        "SELECT * FROM fila.parametro_organica WHERE sede = ANY(%(sedes)s)", {"sedes": lista})}
    franjas = _leer(
        """SELECT sede, dia_semana, desde, hasta FROM fila.franja_organica
            WHERE sede = ANY(%(sedes)s) ORDER BY dia_semana, desde""", {"sedes": lista})
    estados = {e["sede"]: e for e in _leer(tablero_fila.ESTADO_ORGANICA, {"sedes": lista})}
    sesiones = _leer(
        """SELECT sede, abierta_en, abierta_por, abierta_desde, cerrada_en, cerrada_por, cerrada_desde
             FROM fila.sesion_organica WHERE sede = ANY(%(sedes)s)
            ORDER BY abierta_en DESC LIMIT 30""", {"sedes": lista})
    return {"sedes": [{
        "sede": s,
        "nombre": NOMBRES.get(s, s.replace("-", " ").title()),
        "parametros": parametros.get(s) or _por_defecto(s),
        "franjas": [{"dia": f["dia_semana"], "desde": f["desde"], "hasta": f["hasta"]}
                    for f in franjas if f["sede"] == s],
        "estado": estados.get(s),
        "sesiones": [x for x in sesiones if x["sede"] == s][:10],
    } for s in lista]}


@router.put("/{sede}")
def guardar(sede: str, entrada: Parametros, sesion: GestionaTurnos):
    _sede_valida(sede)
    if not tablero_fila._dsn:
        raise HTTPException(503, "Los datos de la fila no están conectados.")
    try:
        with psycopg.connect(tablero_fila._dsn, row_factory=dict_row, connect_timeout=5) as cn:
            cn.execute(
                "SELECT * FROM fila.fijar_parametro_organica(%s, %s, %s, %s, %s, %s, %s)",
                (sede, entrada.recibe_organica, entrada.quien_abre, entrada.modo_franjas,
                 entrada.inicio_cosecha, entrada.dias_prioridad, sesion.actor))
            cn.execute(
                "SELECT * FROM fila.fijar_franjas_organica(%s, %s::smallint[], %s::time[], %s::time[], %s)",
                (sede, [f.dia for f in entrada.franjas], [f.desde for f in entrada.franjas],
                 [f.hasta for f in entrada.franjas], sesion.actor))
    except psycopg.errors.RaiseException as exc:
        raise HTTPException(409, exc.diag.message_primary or "No se pudo guardar.") from exc
    except psycopg.Error as exc:
        raise HTTPException(503, "No se pudo guardar en la fila.") from exc
    return {"ok": True}


@router.post("/{sede}/{accion}")
def abrir_o_cerrar(sede: str, accion: str, sesion: Opera):
    if accion not in {"abrir", "cerrar"}:
        raise HTTPException(404)
    _sede_valida(sede)
    funcion = "abrir_sesion_organica" if accion == "abrir" else "cerrar_sesion_organica"
    _escribir(f"SELECT id FROM fila.{funcion}(%(sede)s, %(actor)s, 'bascula')",
              {"sede": sede, "actor": sesion.actor})
    return next((e for e in _leer(tablero_fila.ESTADO_ORGANICA, {"sedes": [sede]})), None)
