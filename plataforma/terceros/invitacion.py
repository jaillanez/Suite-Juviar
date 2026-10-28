"""Validación pura de invitaciones por código ligado al teléfono."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

VIGENCIA = timedelta(minutes=30)
MAX_INTENTOS = 3


def generar_codigo() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_codigo(codigo: str, pimienta: str) -> str:
    return hmac.new(pimienta.encode(), codigo.encode(), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class Invitacion:
    clientecuit: str
    telefono_invitado: str
    codigo_hash: str
    creada_en: datetime
    intentos: int
    estado: str


class Rechazo(ValueError):
    pass


def validar_intento(
    invitacion: Invitacion,
    telefono: str,
    codigo: str,
    pimienta: str,
    ahora: datetime,
) -> str:
    if invitacion.estado != "pendiente":
        raise Rechazo("la invitación ya no está vigente")
    if ahora - invitacion.creada_en > VIGENCIA:
        raise Rechazo("vencida")
    if telefono != invitacion.telefono_invitado:
        raise Rechazo("el código no corresponde a este número")
    if hmac.compare_digest(hash_codigo(codigo.strip(), pimienta), invitacion.codigo_hash):
        return "consumida"
    return "anulada" if invitacion.intentos + 1 >= MAX_INTENTOS else "pendiente"
