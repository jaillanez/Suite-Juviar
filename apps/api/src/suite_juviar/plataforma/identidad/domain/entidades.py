"""Personas internas. El dueño del dato es Nexus (servidor de Santa Fe).

Regla de la Base Común §3.1: el legajo de Nexus es la clave única de todo
empleado. Ningún módulo crea, edita ni guarda su propia lista de personal.

Por eso `Legajo` es inmutable y el repositorio no expone escritura: la
imposibilidad de duplicar el maestro está en el tipo, no en un documento.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Empresa(StrEnum):
    ENAV = "ENAV"
    JUBIAR = "JUBIAR"
    # PENDIENTE §3.4: confirmar razón social y CUIT de la segunda unidad
    # (aparece como ENAV y como ANAP en la documentación relevada).


class TipoVinculo(StrEnum):
    PERMANENTE = "PERMANENTE"
    TEMPORARIO_COSECHA = "TEMPORARIO_COSECHA"


@dataclass(frozen=True, slots=True)
class NumeroLegajo:
    valor: str

    def __post_init__(self) -> None:
        if not self.valor.strip():
            raise ValueError("El número de legajo no puede ser vacío")


@dataclass(frozen=True, slots=True)
class Legajo:
    """Proyección de solo lectura del maestro de Nexus.

    No tiene setters ni métodos de mutación. Cualquier corrección de nombre,
    DNI, puesto o sector se hace en Nexus y llega por la vista SQL.
    """

    numero: NumeroLegajo
    nombre: str
    apellido: str
    dni: str
    puesto: str
    sector: str
    empresa: Empresa
    tipo_vinculo: TipoVinculo
    fecha_ingreso: date | None
    activo: bool

    @property
    def nombre_completo(self) -> str:
        return f"{self.apellido}, {self.nombre}"
