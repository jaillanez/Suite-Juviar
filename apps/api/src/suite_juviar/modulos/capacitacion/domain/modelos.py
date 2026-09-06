from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID


def _obligatorio(nombre: str, valor: str) -> None:
    if not valor or not valor.strip():
        raise ValueError(f"{nombre} no puede estar vacío")


@dataclass(frozen=True, slots=True)
class Tema:
    id: str
    nombre: str
    horas: float

    def __post_init__(self) -> None:
        _obligatorio("El identificador del tema", self.id)
        _obligatorio("El nombre del tema", self.nombre)
        if isinstance(self.horas, bool) or not isinstance(self.horas, int | float) or self.horas <= 0:
            raise ValueError("Las horas del tema deben ser mayores a cero")


@dataclass(frozen=True, slots=True)
class Dictado:
    id: str
    tema_id: str
    fecha: date
    instructor: str

    def __post_init__(self) -> None:
        _obligatorio("El identificador del dictado", self.id)
        _obligatorio("El tema del dictado", self.tema_id)
        _obligatorio("El instructor", self.instructor)


@dataclass(frozen=True, slots=True)
class Participante:
    legajo: str
    nombre_completo: str
    supervisor: bool = False

    def __post_init__(self) -> None:
        _obligatorio("El legajo", self.legajo)
        _obligatorio("El nombre", self.nombre_completo)


@dataclass(frozen=True, slots=True)
class Asistencia:
    dictado_id: str
    participante: Participante
    presente: bool
    firma_id: UUID | None
    estado_firma: str

    def __post_init__(self) -> None:
        _obligatorio("El dictado", self.dictado_id)
        _obligatorio("El estado de firma", self.estado_firma)
        if not self.presente and self.firma_id is not None:
            raise ValueError("Una ausencia no puede tener firma de asistencia")


@dataclass(frozen=True, slots=True)
class AlertaSupervisor:
    tema_id: str
    legajo: str
    porcentaje: float
    umbral: float


@dataclass(frozen=True, slots=True)
class AnulacionAsistencia:
    dictado_id: str
    legajo: str
    motivo: str
    anulada_por: str
    anulada_en: datetime

    def __post_init__(self) -> None:
        _obligatorio("El dictado", self.dictado_id)
        _obligatorio("El legajo", self.legajo)
        _obligatorio("El motivo", self.motivo)
        _obligatorio("El actor", self.anulada_por)
