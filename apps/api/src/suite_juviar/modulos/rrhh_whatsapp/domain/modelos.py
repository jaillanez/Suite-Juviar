"""Bandeja de RRHH: lo que el personal manda por WhatsApp (certificado médico o pedido de EPP).

Nada pasa solo al legajo: cada mensaje queda pendiente de revisión hasta que RRHH lo resuelve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class TipoMensaje(StrEnum):
    CERTIFICADO = "certificado"
    EPP = "epp"


class EstadoMensaje(StrEnum):
    PENDIENTE = "PENDIENTE"
    EN_LEGAJO = "EN_LEGAJO"  # certificado guardado como adjunto del legajo
    ATENDIDO = "ATENDIDO"  # pedido de EPP resuelto
    DESCARTADO = "DESCARTADO"


# Respuesta del empleado a lo que se leyó de su certificado (infra/042).
CONFIRMACIONES = ("sin_pedir", "esperando", "corrigiendo", "confirmado", "no_coincide")
TIPOS_ARCHIVO = ("application/pdf", "image/jpeg", "image/png", "image/webp")
EXTENSIONES = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


@dataclass(frozen=True, slots=True)
class MensajeRRHH:
    id: str
    telefono: str
    legajo: str
    nombre: str
    empresa: str
    tipo: TipoMensaje
    texto: str
    recibido_en: datetime
    archivo: bytes | None = None
    archivo_tipo: str = ""
    archivo_nombre: str = ""
    # Lo que leyó el lector de certificados; RRHH lo confirma o corrige antes de pasarlo al legajo.
    lectura: dict[str, Any] | None = None
    lectura_error: str = ""
    aviso_pendiente: bool = False  # todavía no se le pudo mandar al empleado lo que se leyó
    confirmacion: str = "sin_pedir"
    confirmacion_vence: datetime | None = None
    correccion: str = ""
    respondido_en: datetime | None = None
    estado: EstadoMensaje = EstadoMensaje.PENDIENTE
    resuelto_por: str = ""
    resuelto_en: datetime | None = None
    nota: str = ""
    adjunto_id: str | None = None
    datos_confirmados: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.archivo is not None and self.archivo_tipo not in TIPOS_ARCHIVO:
            raise ValueError("Tipo de archivo no admitido.")
        if self.confirmacion not in CONFIRMACIONES:
            raise ValueError("Estado de confirmación desconocido.")


@dataclass(frozen=True, slots=True)
class MensajeEntrante:
    """Lo que el bot dejó en la DMZ."""

    id: str
    telefono: str
    legajo: str
    nombre: str
    empresa: str
    tipo: str
    texto: str
    recibido_en: datetime
    archivo: bytes | None = None
    archivo_tipo: str = ""
    archivo_nombre: str = ""


@dataclass(frozen=True, slots=True)
class Confirmacion:
    confirmacion: str
    vence: datetime | None
    correccion: str
    respondido_en: datetime | None


@dataclass(frozen=True, slots=True)
class CVEntrante:
    id: str
    telefono: str
    nombre_archivo: str
    contenido: bytes
    tipo: str
    recibido_en: datetime
