from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AltaPublica(BaseModel):
    sede: str = Field(pattern=r"^[a-z0-9_-]{2,30}$")
    patente: str = Field(min_length=5, max_length=20)
    productor: str = Field(min_length=2, max_length=120)
    telefono: str | None = Field(default=None, pattern=r"^[0-9]{8,20}$")
    id_cliente: UUID


class Confirmacion(BaseModel):
    id_cliente: UUID
    clientecuit: str = Field(min_length=5, max_length=40)
    clientecodigo: str | None = Field(default=None, max_length=60)
    declara_organica: bool = False
    productor_revision_manual: bool = False
    momento_cliente: datetime


class AltaGuardia(Confirmacion):
    sede: str = Field(pattern=r"^[a-z0-9_-]{2,30}$")
    patente: str = Field(min_length=5, max_length=20)
    productor: str = Field(min_length=2, max_length=120)
    telefono: str | None = Field(default=None, pattern=r"^[0-9]{8,20}$")


class Accion(BaseModel):
    id_cliente: UUID
    momento_cliente: datetime
    motivo: str | None = Field(default=None, max_length=120)


class PedidoTurno(BaseModel):
    sede: str = Field(pattern=r"^[a-z0-9_-]{2,30}$")
    fecha: str
    clientecuit: str = Field(min_length=5, max_length=40)
    clientecodigo: str | None = Field(default=None, max_length=60)
    camiones: int = Field(ge=1, le=50)
    kg_por_camion: int = Field(ge=1000, le=40000)
    declara_organica: bool = False
    pedido_por: str = Field(min_length=3, max_length=100)
    canal: Literal["whatsapp", "web", "bodega"] = "web"


class IngresoGuardia(BaseModel):
    usuario: str = Field(pattern=r"^[a-z0-9._-]{3,30}$")
    clave: str = Field(min_length=1, max_length=200)


class CambioClave(BaseModel):
    actual: str = Field(min_length=1, max_length=200)
    nueva: str = Field(min_length=6, max_length=200)
