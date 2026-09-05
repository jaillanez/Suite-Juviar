"""Bitácora de auditoría. Inmutable por construcción y por motor.

Regla 5 de construcción (§6.1): toda operación que cree o modifique datos deja
bitácora. Dos capas de defensa:

1. Acá: `AsientoBitacora` es frozen y el puerto no tiene `actualizar` ni
   `eliminar`. No hay forma de expresar una modificación en el código.
2. En la base: al rol de aplicación se le revocan UPDATE y DELETE sobre
   `bitacora.asiento` (ver sql/10_bitacora_inmutable.sql). Aunque alguien
   escriba SQL crudo, el motor lo rechaza.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class TipoActor(StrEnum):
    EMPLEADO = "EMPLEADO"          # identificado por legajo de Nexus
    TERCERO = "TERCERO"            # identificado por CUIT
    SISTEMA = "SISTEMA"            # procesos automáticos, worker de outbox


@dataclass(frozen=True, slots=True)
class Actor:
    tipo: TipoActor
    identificador: str


@dataclass(frozen=True, slots=True)
class AsientoBitacora:
    """Un hecho ocurrido. No se corrige: se agrega otro asiento."""

    accion: str                      # "epp.entrega.registrada"
    actor: Actor
    entidad: str                     # "constancia_epp"
    entidad_id: str
    modulo: str
    datos: dict[str, Any] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    ocurrido_en: datetime = field(default_factory=lambda: datetime.now(UTC))
