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
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import exigir_permiso
from suite_juviar.plataforma.identidad.domain.sesion import Sesion

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


# --- Datos reales para Recepción (misma base y mismo rol de sólo lectura) ------------------
recepcion = APIRouter(prefix="/recepcion-datos", tags=["recepción"])
PuedeRecibir = Annotated[object, Depends(exigir_permiso("recepcion.romaneo.crear"))]


def _leer(consulta: str, parametros: dict[str, Any]) -> list[dict[str, Any]]:
    if not _dsn:
        raise HTTPException(503, "Los datos de la fila no están conectados.")
    try:
        with psycopg.connect(_dsn, row_factory=dict_row, connect_timeout=5) as cn:
            return [dict(f) for f in cn.execute(consulta, parametros).fetchall()]
    except psycopg.Error as exc:
        raise HTTPException(503, "No se pudieron leer los datos de la fila.") from exc


@recepcion.get("/productores")
def buscar_productores(_: PuedeRecibir, q: str = ""):
    texto = q.strip()
    if len(texto) < 2:
        return []
    digitos = "".join(c for c in texto if c.isdigit())
    filas = _leer(
        """SELECT clientecuit, razonsocial, codigos, ultima_entrega FROM fila.productor
            WHERE razonsocial ILIKE %(nombre)s OR (%(cuit)s <> '' AND clientecuit LIKE %(cuit)s)
               OR %(texto)s = ANY(codigos)
            ORDER BY ultima_entrega DESC NULLS LAST, razonsocial LIMIT 15""",
        {"nombre": f"%{texto}%", "cuit": f"{digitos}%" if len(digitos) >= 3 else "", "texto": texto.upper()},
    )
    return [{"cuit": f["clientecuit"], "razon_social": f["razonsocial"], "codigos": f["codigos"],
             "ultima_entrega": f["ultima_entrega"]} for f in filas]


@recepcion.get("/variedades")
def variedades(_: PuedeRecibir):
    filas = _leer(
        """SELECT variedad, count(*) AS n FROM consulta.descarga_publica
            WHERE variedad IS NOT NULL AND btrim(variedad) <> ''
            GROUP BY variedad ORDER BY n DESC, variedad LIMIT 80""",
        {},
    )
    return [f["variedad"] for f in filas]


@recepcion.get("/camiones")
def camiones_en_fila(_: PuedeRecibir, sede: str = "chimbas"):
    if sede not in sedes():
        raise HTTPException(404, "Sede inexistente.")
    filas = _leer(
        """SELECT v.id, v.numero_dia, v.patente, v.patente_acoplado, v.clientecuit, v.chofer_dni,
                  v.chofer_nombre, v.productor_texto, v.variedad_declarada, v.estado,
                  p.razonsocial
             FROM fila.viaje v LEFT JOIN fila.productor p ON p.clientecuit = v.clientecuit
            WHERE v.sede = %(sede)s AND v.estado IN ('en_espera', 'llamado', 'en_bascula')
            ORDER BY v.estado = 'en_espera', v.numero_dia NULLS LAST""",
        {"sede": sede},
    )
    return [{**f, "productor": f["razonsocial"] or f["productor_texto"]} for f in filas]


# --- Calendario de turnos de la bodega -------------------------------------------------
# Lectura con consultas; escritura sólo con las funciones de infra/029, que aplican las
# reglas de cupo de la fila dentro de la base.
turnos = APIRouter(prefix="/turnos-bodega", tags=["turnos de cosecha"])
GestionaTurnos = Annotated[Sesion, Depends(exigir_permiso("fila.turnos.gestionar"))]


class CapacidadEntrada(BaseModel):
    sede: str
    fecha: date | None = None
    kg_dia: int = Field(ge=0, le=10_000_000)


class TurnoEntrada(BaseModel):
    sede: str
    fecha: date
    cuit: str = Field(pattern=r"^\d{11}$")
    codigo: str | None = Field(default=None, max_length=60)
    camiones: int = Field(ge=1, le=50)
    kg_por_camion: int = Field(ge=1000, le=40000)
    organica: bool = False


def _escribir(consulta: str, parametros: dict[str, Any]) -> dict[str, Any]:
    if not _dsn:
        raise HTTPException(503, "Los datos de la fila no están conectados.")
    try:
        with psycopg.connect(_dsn, row_factory=dict_row, connect_timeout=5) as cn:
            fila = cn.execute(consulta, parametros).fetchone()
    except psycopg.errors.RaiseException as exc:
        raise HTTPException(409, exc.diag.message_primary or "No se pudo guardar.") from exc
    except psycopg.Error as exc:
        raise HTTPException(503, "No se pudo guardar en la fila.") from exc
    return dict(fila) if fila else {}


def _sede_valida(sede: str) -> str:
    if sede not in sedes():
        raise HTTPException(404, "Sede inexistente.")
    return sede


@turnos.get("/productores")
def productores_turnos(_: GestionaTurnos, q: str = ""):
    return buscar_productores(None, q)


@turnos.get("/mes")
def mes_turnos(_: GestionaTurnos, sede: str, mes: str = Query(pattern=r"^\d{4}-\d{2}$")):
    _sede_valida(sede)
    inicio = date.fromisoformat(f"{mes}-01")
    fin = date(inicio.year + (inicio.month == 12), inicio.month % 12 + 1, 1)
    capacidades = _leer("SELECT fecha, kg_dia FROM fila.capacidad WHERE sede = %(sede)s", {"sede": sede})
    por_defecto = next((c["kg_dia"] for c in capacidades if c["fecha"] is None), None)
    por_fecha = {c["fecha"]: c["kg_dia"] for c in capacidades if c["fecha"] is not None}
    filas = _leer(
        """SELECT t.id, t.fecha, t.clientecuit, t.clientecodigo, t.camiones, t.camiones_usados,
                  t.kg_por_camion, t.declara_organica, t.estado, t.pedido_por, t.canal,
                  p.razonsocial
             FROM fila.turno t LEFT JOIN fila.productor p ON p.clientecuit = t.clientecuit
            WHERE t.sede = %(sede)s AND t.fecha >= %(inicio)s AND t.fecha < %(fin)s
            ORDER BY t.fecha, t.creado_en""",
        {"sede": sede, "inicio": inicio, "fin": fin},
    )
    dias = []
    dia = inicio
    while dia < fin:
        del_dia = [f for f in filas if f["fecha"] == dia]
        dias.append({
            "fecha": dia.isoformat(),
            "capacidad_kg": por_fecha.get(dia, por_defecto),
            "capacidad_propia": dia in por_fecha,
            "reservado_kg": sum(f["camiones"] * f["kg_por_camion"] for f in del_dia if f["estado"] == "activo"),
            "turnos": [{
                "id": f["id"], "cuit": f["clientecuit"], "productor": f["razonsocial"] or f["clientecuit"],
                "codigo": f["clientecodigo"], "camiones": f["camiones"], "camiones_usados": f["camiones_usados"],
                "kg_por_camion": f["kg_por_camion"], "organica": f["declara_organica"], "estado": f["estado"],
                "pedido_por": f["pedido_por"], "canal": f["canal"],
            } for f in del_dia],
        })
        dia = date.fromordinal(dia.toordinal() + 1)
    return {"sede": sede, "mes": mes, "capacidad_por_defecto_kg": por_defecto, "dias": dias}


@turnos.put("/capacidad")
def fijar_capacidad(entrada: CapacidadEntrada, sesion: GestionaTurnos):
    _sede_valida(entrada.sede)
    return _escribir(
        "SELECT * FROM fila.fijar_capacidad(%(sede)s, %(fecha)s, %(kg)s, %(actor)s)",
        {"sede": entrada.sede, "fecha": entrada.fecha, "kg": entrada.kg_dia, "actor": sesion.actor},
    )


@turnos.post("", status_code=201)
def anotar_turno(entrada: TurnoEntrada, sesion: GestionaTurnos):
    _sede_valida(entrada.sede)
    return _escribir(
        """SELECT * FROM fila.reservar_turno_bodega(%(sede)s, %(fecha)s, %(cuit)s, %(codigo)s,
               %(camiones)s, %(kg)s, %(organica)s, %(actor)s)""",
        {"sede": entrada.sede, "fecha": entrada.fecha, "cuit": entrada.cuit, "codigo": entrada.codigo,
         "camiones": entrada.camiones, "kg": entrada.kg_por_camion, "organica": entrada.organica,
         "actor": sesion.actor},
    )


@turnos.post("/{turno_id}/cancelar")
def cancelar_turno(turno_id: int, sesion: GestionaTurnos):
    return _escribir("SELECT * FROM fila.cancelar_turno(%(id)s, %(actor)s)",
                     {"id": turno_id, "actor": sesion.actor})
