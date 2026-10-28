"""Terceros externos: productores, transportistas, compradores, choferes y vehículos.

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
    COMPRADOR_EXTERIOR = "COMPRADOR_EXTERIOR"
    POSTULANTE = "POSTULANTE"


DUENO_POSTULANTES = "RRHH"


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
    cuit: CUIT | None
    razon_social: str
    tipo: TipoTercero
    id: UUID = field(default_factory=uuid4)
    activo: bool = True
    pais: str = "AR"
    identificacion_fiscal: str | None = None
    email: str | None = None
    dni: str | None = None
    legajo_vinculado: str | None = None

    # PENDIENTE §3.3 / Ley 9133 (Mendoza): definir con el asesor legal qué
    # documentación se exige al productor tercero y qué queda registrado.
    # Sin esa definición, `VerificacionDocumental` queda declarativa.
    verificacion_vigente_hasta: date | None = None

    def __post_init__(self) -> None:
        if self.tipo in {TipoTercero.PRODUCTOR, TipoTercero.TRANSPORTISTA} and self.cuit is None:
            raise ValueError("Productores y transportistas requieren CUIT")
        if self.tipo is TipoTercero.COMPRADOR_EXTERIOR:
            if not self.pais or self.pais == "AR":
                raise ValueError("El comprador exterior requiere un país distinto de AR")
            if not self.email:
                raise ValueError("El comprador exterior requiere email")
        if self.tipo is TipoTercero.POSTULANTE:
            dni = (self.dni or "").strip()
            email = (self.email or "").strip()
            if not dni and not email:
                raise ValueError("El postulante requiere DNI o correo")
            if dni and not dni.isdigit():
                raise ValueError("El DNI del postulante sólo puede contener dígitos")

    def verificacion_al_dia(self, al: date) -> bool:
        return (
            self.verificacion_vigente_hasta is not None
            and self.verificacion_vigente_hasta >= al
        )

    @property
    def clave_registro(self) -> tuple[str, str]:
        """Identidad canónica que debe proteger el repositorio con unicidad."""
        if self.identificacion_fiscal:
            return self.pais.upper(), self.identificacion_fiscal.strip().upper()
        if self.tipo is TipoTercero.POSTULANTE and self.dni and self.dni.strip():
            return "AR-DNI", self.dni.strip()
        if self.tipo is TipoTercero.COMPRADOR_EXTERIOR and self.email:
            return "EMAIL", self.email.strip().casefold()
        if self.tipo is TipoTercero.POSTULANTE and self.email and self.email.strip():
            return "EMAIL", self.email.strip().casefold()
        if self.cuit:
            return "AR", self.cuit.valor.replace("-", "")
        raise ValueError("El tercero no tiene una identificación utilizable")

    def vincular_alta_en_nexus(self, legajo: str) -> None:
        if self.tipo is not TipoTercero.POSTULANTE:
            raise ValueError("Sólo un postulante puede vincularse a un alta de Nexus")
        if not legajo or not legajo.strip():
            raise ValueError("El legajo vinculado no puede estar vacío")
        self.legajo_vinculado = legajo.strip()


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
