"""Tablero de la fila de camiones de todas las bodegas, en sólo lectura.

Lee la base DMZ con el rol `gestion_tablero` (infra/027): sólo SELECT sobre los viajes
y sobre la variedad, el neto y el azúcar que informó la báscula.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row

from suite_juviar.plataforma.identidad.api.dependencias import exigir_permiso

ZONA = ZoneInfo("America/Argentina/San_Juan")
ACTIVOS = ("pendiente", "en_espera", "llamado", "en_bascula")
NOMBRES = {"chimbas": "Chimbas", "lavalle": "Lavalle", "media-agua": "Media Agua"}

router = APIRouter(prefix="/fila-tablero", tags=["fila"])
_dsn = ""


def configurar(dsn: str) -> None:
    global _dsn
    _dsn = dsn


def sedes() -> list[str]:
    valor = os.getenv("SJ_FILA_SEDES", "chimbas,lavalle,media-agua")
    return [s.strip() for s in valor.split(",") if s.strip()]


Autorizado = Annotated[object, Depends(exigir_permiso("fila.tablero.leer"))]

CONSULTA = """
SELECT v.sede, v.numero_dia, v.patente, v.productor_texto, v.estado, v.declara_organica,
       v.variedad_declarada, v.registrado_en, v.confirmado_en, v.llamado_en,
       v.en_bascula_en, v.cerrado_en,
       d.variedad AS variedad_bascula, d.neto, d.azucar
  FROM fila.viaje v
  LEFT JOIN consulta.descarga_publica d ON d.id_suite = v.descarga_id
 WHERE v.sede = ANY(%(sedes)s)
   AND (v.estado = ANY(%(activos)s)
        OR (v.registrado_en AT TIME ZONE 'America/Argentina/San_Juan')::date = %(hoy)s)
 ORDER BY v.sede, v.numero_dia NULLS LAST, v.registrado_en
"""


def _del_dia(momento: datetime | None, hoy: date) -> bool:
    return momento is not None and momento.astimezone(ZONA).date() == hoy


def armar_tablero(filas: list[dict[str, Any]], hoy: date, lista_sedes: list[str]) -> dict[str, Any]:
    """Agrupa los viajes por bodega, con los números del día. Sin base: se prueba suelto."""
    por_sede: dict[str, list[dict[str, Any]]] = {s: [] for s in lista_sedes}
    for fila in filas:
        if fila["sede"] in por_sede:  # sólo las bodegas configuradas
            por_sede[fila["sede"]].append(fila)
    resultado = []
    for sede, viajes in por_sede.items():
        del_dia = [v for v in viajes if _del_dia(v["registrado_en"], hoy)]
        resultado.append({
            "sede": sede,
            "nombre": NOMBRES.get(sede, sede.replace("-", " ").title()),
            "anotados_hoy": sum(v["estado"] != "cancelado" for v in del_dia),
            "en_espera": sum(v["estado"] in ("pendiente", "en_espera") for v in viajes),
            "llamados": sum(v["estado"] == "llamado" for v in viajes),
            "en_bascula": sum(v["estado"] == "en_bascula" for v in viajes),
            "descargados_hoy": sum(v["estado"] == "descargado" for v in del_dia),
            "camiones": [
                {
                    "numero": v["numero_dia"],
                    "patente": v["patente"],
                    "productor": v["productor_texto"],
                    "estado": v["estado"],
                    "organico": v["declara_organica"],
                    "variedad_declarada": v["variedad_declarada"],
                    "variedad_bascula": v["variedad_bascula"],
                    "neto": v["neto"],
                    "azucar": float(v["azucar"]) if v["azucar"] is not None else None,
                    "registrado_en": v["registrado_en"],
                    "llamado_en": v["llamado_en"],
                }
                for v in viajes
                if v["estado"] != "cancelado"
            ],
        })
    return {"fecha": hoy.isoformat(), "sedes": resultado}


@router.get("")
def tablero(_: Autorizado):
    if not _dsn:
        raise HTTPException(503, "El tablero de la fila no está conectado.")
    hoy = datetime.now(ZONA).date()
    try:
        with psycopg.connect(_dsn, row_factory=dict_row, connect_timeout=5) as cn:
            filas = cn.execute(CONSULTA, {"activos": list(ACTIVOS), "hoy": hoy, "sedes": sedes()}).fetchall()
    except psycopg.Error as exc:
        raise HTTPException(503, "No se pudo leer la fila de camiones.") from exc
    return armar_tablero([dict(f) for f in filas], hoy, sedes())
