from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from suite_juviar.modulos.recepcion.application.casos_uso import (
    AbrirRomaneo,
    DatosIngreso,
)
from suite_juviar.modulos.recepcion.domain.entidades import OrigenPeso
from suite_juviar.modulos.recepcion.infrastructure.dependencias import abrir_romaneo
from suite_juviar.plataforma.identidad.api.dependencias import exigir_permiso

router = APIRouter(
    prefix="/recepcion",
    tags=["recepción"],
    dependencies=[Depends(exigir_permiso("recepcion.romaneo.crear"))],
)


class IngresoIn(BaseModel):
    productor_cuit: str
    transportista_cuit: str
    chofer_dni: str
    patente_chasis: str
    patente_acoplado: str | None = None
    variedad: str
    finca: str | None = None
    bruto_kg: Decimal
    origen_peso: OrigenPeso
    operador_legajo: str


class RomaneoOut(BaseModel):
    id: str
    numero: int
    estado: str


@router.post("/romaneos", response_model=RomaneoOut, status_code=201)
async def abrir(payload: IngresoIn, caso: Annotated[AbrirRomaneo, Depends(abrir_romaneo)]):
    romaneo = await caso(DatosIngreso(**payload.model_dump()))
    return RomaneoOut(id=str(romaneo.id), numero=romaneo.numero, estado=romaneo.estado)
