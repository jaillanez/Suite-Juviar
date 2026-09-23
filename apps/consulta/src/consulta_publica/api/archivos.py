"""Entrega opaca y temporal de medios que descarga Meta."""
from __future__ import annotations

import re
from typing import Annotated

from consulta_publica.bot.repositorio import RepositorioArchivos
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

router = APIRouter(tags=["archivos temporales"])
_repositorio: RepositorioArchivos | None = None


def configurar(repositorio: RepositorioArchivos) -> None:
    global _repositorio
    _repositorio = repositorio


def obtener() -> RepositorioArchivos:
    if _repositorio is None:
        raise HTTPException(503, "archivos no configurados")
    return _repositorio


Repo = Annotated[RepositorioArchivos, Depends(obtener)]


@router.get("/archivos/{token}.{extension}")
def descargar(token: str, extension: str, repo: Repo):
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,60}", token) or extension not in {"png", "pdf"}:
        raise HTTPException(404, "archivo inexistente o vencido")
    fila = repo.leer(token)
    if not fila or fila["extension"] != extension:
        raise HTTPException(404, "archivo inexistente o vencido")
    nombre = re.sub(r"[^A-Za-z0-9._-]", "_", fila["nombre"])
    disposicion = "inline" if extension == "png" else "attachment"
    return Response(
        bytes(fila["contenido"]),
        media_type="image/png" if extension == "png" else "application/pdf",
        headers={
            "Content-Disposition": f'{disposicion}; filename="{nombre}"',
            "Cache-Control": "private, no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
        },
    )
