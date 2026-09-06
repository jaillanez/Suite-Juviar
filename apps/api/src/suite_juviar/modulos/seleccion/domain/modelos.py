"""Modelos puros para conservar los CV originales."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

DUENO_DATO = "RRHH"


class OrigenCV(StrEnum):
    CARPETA_CHIMBAS = "CARPETA_CHIMBAS"
    CORREO = "CORREO"


@dataclass(frozen=True, slots=True)
class DocumentoEntrante:
    origen: OrigenCV
    referencia_fuente: str
    nombre_archivo: str
    contenido: bytes
    recibido_en: datetime
    fuente_simulada: bool

    def __post_init__(self) -> None:
        if not self.referencia_fuente or not self.referencia_fuente.strip():
            raise ValueError("La referencia de fuente no puede estar vacía")
        if not self.nombre_archivo or not self.nombre_archivo.strip():
            raise ValueError("El nombre del CV no puede estar vacío")
        if not self.contenido:
            raise ValueError("El archivo original no puede estar vacío")


@dataclass(frozen=True, slots=True)
class CVOriginal:
    id: str
    origen: OrigenCV
    referencia_fuente: str
    nombre_archivo: str
    contenido: bytes
    sha256: str
    recibido_en: datetime
    incorporado_en: datetime
    dueno_dato: str = DUENO_DATO
    fuente_simulada: bool = True
