"""Sesión de uva orgánica de una bodega, sin dependencias de base ni red.

Reglas (reunión del 15-11):
* Con la sesión abierta no se llama ni pasa a báscula un camión convencional.
* La orgánica que entra sin sesión abierta se recibe como convencional.
* La orgánica va primero en la fila con la sesión abierta o durante los primeros días de
  cosecha; fuera de eso espera como cualquier otro camión.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

BLOQUEO_CONVENCIONAL = (
    "Sesión orgánica abierta: sólo se puede llamar o pasar a báscula uva orgánica certificada."
)


@dataclass(frozen=True)
class EstadoOrganica:
    recibe: bool = False
    abierta: bool = False
    prioridad: bool = False

    @classmethod
    def desde_fila(cls, fila: dict[str, Any] | None) -> EstadoOrganica:
        if not fila:
            return cls()
        return cls(bool(fila["recibe"]), bool(fila["abierta"]), bool(fila["prioridad"]))


def es_organico(declara_organica: bool, clientecuit: str | None, certificados: frozenset[str]) -> bool:
    return bool(declara_organica) and clientecuit in certificados


def certificados_con_prioridad(estado: EstadoOrganica, certificados: frozenset[str]) -> frozenset[str]:
    """Productores cuya orgánica pasa adelante en la fila en este momento."""
    if estado.recibe and (estado.abierta or estado.prioridad):
        return certificados
    return frozenset()


def bloqueo(estado: EstadoOrganica, organico: bool) -> str | None:
    if estado.recibe and estado.abierta and not organico:
        return BLOQUEO_CONVENCIONAL
    return None


def recibida_como(estado: EstadoOrganica, organico: bool) -> str:
    return "organica" if estado.recibe and estado.abierta and organico else "convencional"
