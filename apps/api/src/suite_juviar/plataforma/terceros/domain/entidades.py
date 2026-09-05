"""Terceros externos: productores, transportistas, choferes y vehículos.

Base Común §3.2: el productor que entrega uva y el chofer que trae el camión
no son empleados y no tienen legajo. Viven en su propio registro y los dos
registros nunca se mezclan. Un mismo DNI puede ser empleado y chofer; son dos
entidades distintas del sistema, con permisos distintos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from uuid import UUID, uuid4


class TipoTercero(StrEnum):
    PRODUCTOR = "PRODUCTOR"
    TRANSPORTISTA = "TRANSPORTISTA"


@dataclass(frozen=True, slots=True)
class CUIT:
    valor: str

    def __post_init__(self) -> None:
        digitos = self.valor.replace("-", "")
        if len(digitos) != 11 or not digitos.isdigit():
            raise ValueError(f"CUIT inválido: {self.valor}")


@dataclass(frozen=True, slots=True)
class Patente:
    valor: str


@dataclass(slots=True)
class Tercero:
    cuit: CUIT
    razon_social: str
    tipo: TipoTercero
    id: UUID = field(default_factory=uuid4)
    activo: bool = True

    # PENDIENTE §3.3 / Ley 9133 (Mendoza): definir con el asesor legal qué
    # documentación se exige al productor tercero y qué queda registrado.
    # Sin esa definición, `VerificacionDocumental` queda declarativa.
    verificacion_vigente_hasta: date | None = None

    def verificacion_al_dia(self, al: date) -> bool:
        return (
            self.verificacion_vigente_hasta is not None
            and self.verificacion_vigente_hasta >= al
        )


@dataclass(slots=True)
class Chofer:
    dni: str
    nombre_completo: str
    transportista: CUIT
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class Vehiculo:
    patente_chasis: Patente
    patente_acoplado: Patente | None
    transportista: CUIT
    id: UUID = field(default_factory=uuid4)
