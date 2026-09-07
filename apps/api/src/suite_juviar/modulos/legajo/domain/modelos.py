from __future__ import annotations

from dataclasses import dataclass

MARCA_SIMULADA = "DATOS SIMULADOS — SIN VALIDEZ"


@dataclass(frozen=True, slots=True)
class PersonaLegajo:
    legajo: str
    nombre_completo: str
    empresa: str
    sector: str
    puesto: str


@dataclass(frozen=True, slots=True)
class Adjunto:
    id: str
    legajo: str
    nombre: str
    contenido: bytes


class FuenteSimuladaEnProduccion(Exception):
    pass
