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
    periodicidad_meses: int | None = None

    def __post_init__(self) -> None:
        _obligatorio("El identificador del tema", self.id)
        _obligatorio("El nombre del tema", self.nombre)
        if (
            isinstance(self.horas, bool)
            or not isinstance(self.horas, int | float)
            or self.horas <= 0
        ):
            raise ValueError("Las horas del tema deben ser mayores a cero")
        if self.periodicidad_meses is not None and self.periodicidad_meses <= 0:
            raise ValueError("La periodicidad debe ser mayor a cero")


@dataclass(frozen=True, slots=True)
class Dictado:
    id: str
    tema_id: str
    fecha: date
    instructor: str
    duracion_horas: float = 1.0
    convocatoria_tipo: str | None = None
    convocatoria_detalle: str | None = None
    convocados: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _obligatorio("El identificador del dictado", self.id)
        _obligatorio("El tema del dictado", self.tema_id)
        _obligatorio("El instructor", self.instructor)
        if self.duracion_horas <= 0:
            raise ValueError("La duración debe ser mayor a cero")
        if self.convocatoria_tipo not in {None, "SECTOR", "PUESTO", "LISTA"}:
            raise ValueError("Tipo de convocatoria inválido")
        if self.convocatoria_tipo and not self.convocados:
            raise ValueError("Una convocatoria debe declarar las personas alcanzadas")


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


FIRMADA_EN_PAPEL = "FIRMADA_EN_PAPEL"


@dataclass(frozen=True, slots=True)
class FilaPlanilla:
    """Una persona tal como se leyó (o se corrigió) en la planilla escaneada."""

    legajo: str
    nombre_completo: str
    presente: bool | None  # None: la lectura no pudo decidir; la define quien revisa


@dataclass(frozen=True, slots=True)
class PlanillaEscaneada:
    id: str
    dictado_id: str
    nombre_archivo: str
    contenido: bytes
    cargada_en: datetime
    cargada_por: str
    filas: tuple[FilaPlanilla, ...]
    motor: str
    mensaje: str
    estado: str = "PENDIENTE"  # PENDIENTE, APROBADA o DESCARTADA
    revisada_por: str | None = None
    revisada_en: datetime | None = None
    motivo_descarte: str | None = None
    resultado: dict | None = None
