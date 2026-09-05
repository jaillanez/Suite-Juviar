"""DTO compartido entre apps/web (DMZ) y modulos/comercial (interno).

Es el ÚNICO módulo que ambos lados pueden importar. Va en un paquete
publicable aparte (`plataforma_dto`) o se duplica a propósito; nunca se
resuelve importando modulos.* desde apps.web.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

Idioma = Literal["es", "en"]


class MetadatosCliente(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    contact_email: EmailStr
    country: str = Field(min_length=2, max_length=100)
    industry_segment: str = Field(max_length=60)


class VolumenProyectado(BaseModel):
    annual_tons: Decimal | None = Field(default=None, ge=0, le=200_000)
    shipment_format: str = Field(max_length=60)


class EspecificacionLaboratorio(BaseModel):
    target_brix: Decimal | None = Field(default=None, ge=0, le=90)
    ph_target: Decimal | None = Field(default=None, ge=0, le=14)
    total_acidity_gl: Decimal | None = Field(default=None, ge=0, le=50)
    so2_free_ppm: Decimal | None = Field(default=None, ge=0, le=500)
    abv_target: Decimal | None = Field(default=None, ge=0, le=25)
    optical_density_420_520: str | None = Field(default=None, max_length=40)


class SolicitudMuestra(BaseModel):
    """Lo que el navegador envía. Sin lead_id: la referencia la asigna el servidor."""

    client_metadata: MetadatosCliente
    product_line: str = Field(max_length=40)
    projected_volume: VolumenProyectado
    lab_specs: EspecificacionLaboratorio
    certifications_required: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("certifications_required")
    @classmethod
    def sin_duplicados(cls, v: list[str]) -> list[str]:
        return sorted(set(v))


class SolicitudAceptada(BaseModel):
    referencia: str
