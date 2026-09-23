"""Entrega de imágenes y PDF a WhatsApp.

Meta no recibe el archivo: recibe un enlace y lo descarga. Ese enlace queda
en internet, así que:
  - lleva un token aleatorio de 32 bytes y no se puede adivinar;
  - vence a los 30 minutos;
  - sólo se sirve mientras está vigente y se borra al vencer.
El archivo vive en la base de la DMZ, no en disco: así lo borra el mismo
worker que limpia el resto y no queda un directorio con datos de productores.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

MINUTOS_VIGENCIA = 30
TIPOS = {"png": "image/png", "pdf": "application/pdf"}
MAXIMO_BYTES = 5 * 1024 * 1024   # WhatsApp: 5 MB en imágenes, 100 MB en documentos


class ArchivoInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Archivo:
    token: str
    extension: str
    nombre: str
    contenido: bytes
    vence: datetime

    @property
    def tipo_mime(self) -> str:
        return TIPOS[self.extension]

    def vigente(self, ahora: datetime) -> bool:
        return ahora < self.vence

    def url(self, base: str) -> str:
        return f"{base.rstrip('/')}/archivos/{self.token}.{self.extension}"


def preparar(contenido: bytes, extension: str, nombre: str, ahora: datetime) -> Archivo:
    if extension not in TIPOS:
        raise ArchivoInvalido(f"tipo no permitido: {extension}")
    if not contenido:
        raise ArchivoInvalido("archivo vacío")
    if len(contenido) > MAXIMO_BYTES:
        raise ArchivoInvalido("el archivo supera el máximo que acepta WhatsApp")
    return Archivo(
        token=secrets.token_urlsafe(32),
        extension=extension,
        nombre=nombre,
        contenido=contenido,
        vence=ahora + timedelta(minutes=MINUTOS_VIGENCIA),
    )


def nombre_reporte(codigo: str, periodo_desde, periodo_hasta) -> str:
    return f"cosecha_{codigo}_{periodo_desde:%Y%m%d}_{periodo_hasta:%Y%m%d}.pdf"
