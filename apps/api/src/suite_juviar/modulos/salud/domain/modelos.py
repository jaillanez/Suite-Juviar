from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

MARCA_SIMULADA = "DATOS SIMULADOS — SIN VALIDEZ"


@dataclass(frozen=True, slots=True)
class Diagnostico:
    codigo: str
    descripcion: str
    padre_codigo: str | None = None


@dataclass(frozen=True, slots=True)
class CertificadoMedico:
    id: str
    legajo: str
    diagnostico_codigo: str
    desde: date
    hasta: date
    dias: int
    profesional: str
    adjunto_id: str


@dataclass(frozen=True, slots=True)
class ConsultaAuditoria:
    id: str
    actor: str
    momento: datetime
    legajo: str | None
    accion: str


@dataclass(frozen=True, slots=True)
class AdjuntoSalud:
    id: str
    nombre: str
    contenido: bytes


class AccesoSaludDenegado(Exception):
    pass


class ReporteNominadoProhibido(Exception):
    pass


class FuenteSimuladaEnProduccion(Exception):
    pass
