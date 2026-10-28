"""Identidad y perfil operativo que recibe la superficie móvil.

La asignación puesto/sector → perfil no vive acá: es un dato administrado por
Parametría y hoy se carga desde un YAML provisorio.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PerfilAcceso(StrEnum):
    CAMPO = "campo"
    DEPOSITO = "deposito"
    BASCULA = "bascula"


@dataclass(frozen=True, slots=True)
class ActorOperativo:
    legajo: str
    nombre_completo: str
    empresa: str
    perfil: PerfilAcceso
