"""API autenticada que Aynux consume desde la DMZ."""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from typing import Protocol

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request

LONGITUD_MINIMA_CLAVE = 32
PATRON_INSCRIPTO = r"^[A-Za-z0-9./-]{1,40}$"


def cargar_clave() -> str:
    clave = os.environ.get("CONSULTA_API_KEY_AYNUX", "")
    if len(clave) < LONGITUD_MINIMA_CLAVE:
        raise RuntimeError(
            f"CONSULTA_API_KEY_AYNUX ausente o menor a {LONGITUD_MINIMA_CLAVE} caracteres"
        )
    return clave


@lru_cache(maxsize=1)
def _clave() -> str:
    return cargar_clave()


def exigir_clave(x_api_key: str | None = Header(default=None)) -> str:
    if not x_api_key or not hmac.compare_digest(x_api_key.encode(), _clave().encode()):
        raise HTTPException(status_code=401, detail="no autorizado")
    return "aynux"


@dataclass(frozen=True)
class Descarga:
    sede: str
    ciu: str
    fecha: datetime | None
    neto: int | None
    variedad: str | None
    azucar: float | None
    estado: str


class Repositorio(Protocol):
    def ultima(self, nroinscripto: str) -> Descarga | None: ...

    def del_dia(self, nroinscripto: str, dia: date) -> list[Descarga]: ...

    def en_descarga(self, nroinscripto: str) -> list[Descarga]: ...

    def rango(
        self, nroinscripto: str, desde: date, hasta: date, limite: int
    ) -> list[Descarga]: ...

    def datos_al(self) -> dict[str, datetime]: ...

    def registrar(
        self, cliente: str, nroinscripto: str, recurso: str, filas: int, ip: str | None
    ) -> None: ...


def obtener_repositorio() -> Repositorio:
    raise RuntimeError("repositorio no configurado")


router = APIRouter(prefix="/v1", tags=["bot"])
Inscripto = Path(..., pattern=PATRON_INSCRIPTO)


def _dto(descarga: Descarga) -> dict:
    return {
        "sede": descarga.sede,
        "ciu": descarga.ciu,
        "fecha": descarga.fecha.isoformat() if descarga.fecha else None,
        "neto_kg": descarga.neto,
        "variedad": descarga.variedad,
        "azucar": descarga.azucar,
        "estado": descarga.estado,
    }


def _datos_al(repo: Repositorio) -> dict:
    return {sede: momento.isoformat() for sede, momento in repo.datos_al().items()}


@router.get("/productores/{nroinscripto}/ultima")
def ultima(
    request: Request,
    nroinscripto: str = Inscripto,
    cliente: str = Depends(exigir_clave),
    repo: Repositorio = Depends(obtener_repositorio),  # noqa: B008
) -> dict:
    descarga = repo.ultima(nroinscripto)
    repo.registrar(cliente, nroinscripto, "ultima", 1 if descarga else 0, _ip(request))
    return {
        "descarga": _dto(descarga) if descarga else None,
        "datos_al": _datos_al(repo),
    }


@router.get("/productores/{nroinscripto}/resumen")
def resumen(
    request: Request,
    nroinscripto: str = Inscripto,
    fecha: date = Query(default_factory=date.today),  # noqa: B008
    cliente: str = Depends(exigir_clave),
    repo: Repositorio = Depends(obtener_repositorio),  # noqa: B008
) -> dict:
    del_dia = repo.del_dia(nroinscripto, fecha)
    en_curso = repo.en_descarga(nroinscripto)
    repo.registrar(
        cliente, nroinscripto, "resumen", len(del_dia) + len(en_curso), _ip(request)
    )
    return {
        "fecha": fecha.isoformat(),
        "descargas": len(del_dia),
        "kilos_netos": sum(descarga.neto or 0 for descarga in del_dia),
        "camiones_en_descarga": len(en_curso),
        "datos_al": _datos_al(repo),
    }


@router.get("/productores/{nroinscripto}/descargas")
def descargas(
    request: Request,
    nroinscripto: str = Inscripto,
    desde: date = Query(...),  # noqa: B008
    hasta: date = Query(...),  # noqa: B008
    limite: int = Query(default=50, ge=1, le=100),
    cliente: str = Depends(exigir_clave),
    repo: Repositorio = Depends(obtener_repositorio),  # noqa: B008
) -> dict:
    if hasta < desde:
        raise HTTPException(status_code=422, detail="hasta es anterior a desde")
    filas = repo.rango(nroinscripto, desde, hasta, limite)
    repo.registrar(cliente, nroinscripto, "descargas", len(filas), _ip(request))
    return {"descargas": [_dto(fila) for fila in filas], "datos_al": _datos_al(repo)}


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None
