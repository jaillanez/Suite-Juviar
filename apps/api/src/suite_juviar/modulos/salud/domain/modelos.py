from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

MARCA_SIMULADA = "DATOS SIMULADOS — SIN VALIDEZ"


@dataclass(frozen=True, slots=True)
class Diagnostico:
    codigo: str
    nombre: str


@dataclass(frozen=True, slots=True)
class CertificadoMedico:
    id: str
    legajo: str
    diagnostico_codigo: str
    desde: date
    hasta: date


@dataclass(frozen=True, slots=True)
class ConsultaAuditoria:
    certificado_id: str
    actor: str
    momento: datetime


class AccesoSaludDenegado(Exception):
    pass


class ReporteNominadoProhibido(Exception):
    pass


class FuenteSimuladaEnProduccion(Exception):
    pass
