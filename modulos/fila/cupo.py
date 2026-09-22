"""Cupo diario estimado en kilos."""
from __future__ import annotations

from dataclasses import dataclass

KG_MIN_CAMION, KG_MAX_CAMION = 1_000, 40_000
MAX_CAMIONES_TURNO = 50
POR_DEFECTO_KG = 11_000


@dataclass(frozen=True)
class Reserva:
    camiones: int
    kg_por_camion: int

    @property
    def kg(self) -> int:
        return self.camiones * self.kg_por_camion


class SinCupo(ValueError):
    def __init__(self, disponibles: int) -> None:
        super().__init__(f"quedan {disponibles} kg para ese día")
        self.disponibles = disponibles


def validar(reserva: Reserva, capacidad_kg: int, reservado_kg: int) -> None:
    if not 1 <= reserva.camiones <= MAX_CAMIONES_TURNO:
        raise ValueError("cantidad de camiones fuera de rango")
    if not KG_MIN_CAMION <= reserva.kg_por_camion <= KG_MAX_CAMION:
        raise ValueError("kilos por camión fuera de rango")
    disponibles = capacidad_kg - reservado_kg
    if reserva.kg > disponibles:
        raise SinCupo(max(disponibles, 0))


def estimado_por_camion(netos_historicos: list[int | None]) -> int:
    validos = [neto for neto in netos_historicos if neto and neto > 0]
    if not validos:
        return POR_DEFECTO_KG
    return int(round(sum(validos) / len(validos), -2))
