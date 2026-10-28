"""Orden de atención de camiones, sin dependencias de base ni red."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

ORGANICO, CON_TURNO, ESPONTANEO = 1, 2, 3
NOMBRE_GRUPO = {ORGANICO: "orgánico", CON_TURNO: "con turno", ESPONTANEO: "espontáneo"}
MOTIVOS_SALTEO = (
    "no_responde",
    "documentacion_incompleta",
    "problema_mecanico",
    "indicacion_de_planta",
    "otro",
)


@dataclass(frozen=True)
class EnEspera:
    id: int
    clientecuit: str
    declara_organica: bool
    con_turno: bool
    confirmado_en: datetime


def grupo(elemento: EnEspera, certificados: frozenset[str]) -> int:
    if elemento.declara_organica and elemento.clientecuit in certificados:
        return ORGANICO
    if elemento.con_turno:
        return CON_TURNO
    return ESPONTANEO


def ordenar(fila: list[EnEspera], certificados: frozenset[str]) -> list[EnEspera]:
    return sorted(fila, key=lambda e: (grupo(e, certificados), e.confirmado_en, e.id))


class SalteoSinMotivo(ValueError):
    pass


def elegir_llamado(
    fila: list[EnEspera],
    certificados: frozenset[str],
    elegido_id: int | None = None,
    motivo: str | None = None,
) -> tuple[EnEspera, list[int]]:
    ordenada = ordenar(fila, certificados)
    if not ordenada:
        raise LookupError("no hay camiones en espera")
    if elegido_id is None or elegido_id == ordenada[0].id:
        return ordenada[0], []
    posicion_elegido = next(
        (indice for indice, elemento in enumerate(ordenada) if elemento.id == elegido_id),
        None,
    )
    if posicion_elegido is None:
        raise LookupError("ese camión no está en espera")
    if motivo not in MOTIVOS_SALTEO:
        raise SalteoSinMotivo("saltear exige un motivo de la lista")
    return ordenada[posicion_elegido], [e.id for e in ordenada[:posicion_elegido]]


def posicion(fila: list[EnEspera], id_: int, certificados: frozenset[str]) -> int | None:
    for indice, elemento in enumerate(ordenar(fila, certificados), start=1):
        if elemento.id == id_:
            return indice
    return None
