"""Celulares del personal de Juviar-ENAV que el bot de WhatsApp reconoce.

Se elige a la persona del legajo (nombre y empresa salen de ahí, no del navegador) y se
marca a mano si es «Personal» o «Mando medio». Se guarda en la DMZ con las funciones de
infra/034, que impiden que un mismo celular sea de un productor y de un empleado.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import SesionActual, exigir_permiso
from suite_juviar.plataforma.terceros.telefono import TelefonoInvalido
from suite_juviar.plataforma.terceros.telefono import normalizar as normalizar_telefono

from .tablero_fila import _escribir, _leer

router = APIRouter(prefix="/personal-bot", tags=["bot"])
Autorizado = Annotated[object, Depends(exigir_permiso("bot.personal.gestionar"))]
EMPRESAS = {"ENAV", "JUBIAR"}

_buscar: Callable[..., list[Any]] | None = None
_obtener: Callable[[str], Any] | None = None


def configurar(buscar: Callable[..., list[Any]], obtener: Callable[[str], Any]) -> None:
    global _buscar, _obtener
    _buscar, _obtener = buscar, obtener


def _legajos() -> tuple[Callable[..., list[Any]], Callable[[str], Any]]:
    if _buscar is None or _obtener is None:
        raise HTTPException(503, "Los legajos no están conectados.")
    return _buscar, _obtener


class Alta(BaseModel):
    telefono: str = Field(min_length=8, max_length=30)
    legajo: str = Field(pattern=r"^[0-9A-Za-z-]{1,20}$")
    tipo: Literal["personal", "mando_medio"]


def _persona(p: Any) -> dict[str, str]:
    return {"legajo": p.legajo, "nombre": p.nombre_completo, "empresa": p.empresa,
            "sector": p.sector, "puesto": p.puesto}


@router.get("")
def listar(_: Autorizado):
    return _leer(
        """SELECT telefono, legajo, nombre, empresa, tipo, activo, alta_por, alta_en,
                  actualizado_por, actualizado_en
             FROM consulta.telefono_personal ORDER BY activo DESC, nombre""",
        {},
    )


@router.get("/personas")
def buscar_personas(_: Autorizado, q: str = ""):
    texto = q.strip()
    if len(texto) < 2:
        return []
    buscar = _legajos()[0]
    encontrados = buscar(legajo=texto) if texto.isdigit() else buscar(apellido=texto)
    return [_persona(p) for p in encontrados[:20]]


@router.get("/{telefono}/historial")
def historial(_: Autorizado, telefono: str = Path(pattern=r"^\d{8,20}$")):
    return _leer(
        """SELECT tipo, actor, antes, despues, momento FROM consulta.personal_evento
            WHERE telefono = %(telefono)s ORDER BY momento DESC LIMIT 50""",
        {"telefono": telefono},
    )


@router.post("", status_code=201)
def guardar(datos: Alta, sesion: SesionActual, _: Autorizado):
    try:
        telefono = normalizar_telefono(datos.telefono)
    except TelefonoInvalido as exc:
        raise HTTPException(422, str(exc)) from exc
    obtener = _legajos()[1]
    persona = obtener(datos.legajo)
    if persona is None:
        raise HTTPException(404, "Ese legajo no existe.")
    empresa = str(persona.empresa).upper()
    if empresa not in EMPRESAS:
        raise HTTPException(409, f"El legajo es de una empresa que el bot no atiende ({persona.empresa}).")
    return _escribir(
        "SELECT * FROM consulta.guardar_personal(%(telefono)s, %(legajo)s, %(nombre)s, %(empresa)s, %(tipo)s, %(actor)s)",
        {"telefono": telefono, "legajo": persona.legajo, "nombre": persona.nombre_completo,
         "empresa": empresa, "tipo": datos.tipo, "actor": sesion.actor},
    )


@router.post("/{telefono}/baja")
def baja(sesion: SesionActual, _: Autorizado, telefono: str = Path(pattern=r"^\d{8,20}$")):
    return _escribir(
        "SELECT * FROM consulta.baja_personal(%(telefono)s, %(actor)s)",
        {"telefono": telefono, "actor": sesion.actor},
    )
