"""API del bot. Solo lectura, y solo de lo propio.

PENDIENTE §7.1: cómo se autentica el consultante (código de operación, CUIT +
clave, o número de romaneo) y por qué canal corre el bot (WhatsApp, Telegram,
web o SMS). Ambas definiciones cambian este archivo, así que está deliberadamente
mínimo.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/consulta", tags=["consulta pública"])


async def consultante_autenticado() -> str:
    """Devuelve el HMAC del CUIT del consultante. Un productor ve sus descargas,
    nunca las del vecino: el filtro se aplica acá, no en el cliente."""
    raise HTTPException(status_code=501, detail="Autenticación pendiente de definición")


@router.get("/mis-descargas")
async def mis_descargas(productor_hmac: str = Depends(consultante_autenticado)):
    raise HTTPException(status_code=501, detail="Etapa 4: requiere recepción en producción")
