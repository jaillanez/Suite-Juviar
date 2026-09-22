from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from modulos.fila.cupo import SinCupo
from modulos.fila.patente import PatenteInvalida

from .modelos import Accion, AltaGuardia, AltaPublica, Confirmacion, PedidoTurno
from .repositorio import RepositorioFila, RepositorioPublico
from .web import MANIFEST, SERVICE_WORKER, guardia, pagina, pantalla, porton, ticket


@lru_cache
def repo_guardia() -> RepositorioFila:
    dsn = os.environ.get("FILA_DSN_GUARDIA", "").strip()
    if not dsn:
        raise RuntimeError("Falta FILA_DSN_GUARDIA")
    return RepositorioFila(dsn)


@lru_cache
def repo_publico() -> RepositorioPublico:
    dsn = os.environ.get("FILA_DSN_PUBLICO", "").strip()
    if not dsn:
        raise RuntimeError("Falta FILA_DSN_PUBLICO")
    return RepositorioPublico(dsn)


@lru_cache
def repo_turnos() -> RepositorioFila:
    dsn = os.environ.get("FILA_DSN_TURNOS", "").strip()
    if not dsn:
        raise RuntimeError("Falta FILA_DSN_TURNOS")
    return RepositorioFila(dsn)


def autenticar_guardia(x_guardia_token: str | None = Header(default=None)) -> str:
    esperado = os.environ.get("FILA_GUARDIA_TOKEN", "")
    if not esperado or x_guardia_token != esperado:
        raise HTTPException(403, "credencial de guardia inválida")
    return "guardia:tablet"


app = FastAPI(
    title="Fila de camiones Juviar",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
GuardiaRepoDep = Annotated[RepositorioFila, Depends(repo_guardia)]
PublicoRepoDep = Annotated[RepositorioPublico, Depends(repo_publico)]
TurnosRepoDep = Annotated[RepositorioFila, Depends(repo_turnos)]
Guardia = Annotated[str, Depends(autenticar_guardia)]


@app.get("/health")
def health() -> dict[str, str]:
    return {"estado": "ok"}


@app.get("/r/{sede}", response_class=HTMLResponse)
def pagina_porton(sede: str) -> str:
    return porton(sede)


@app.get("/t/{token}", response_class=HTMLResponse)
def pagina_ticket(token: str) -> str:
    return ticket(token)


@app.get("/guardia/{sede}", response_class=HTMLResponse)
def pagina_guardia(sede: str) -> str:
    return guardia(sede)


@app.get("/pantalla/{sede}", response_class=HTMLResponse)
def pagina_pantalla(sede: str) -> str:
    return pantalla(sede)


@app.get("/turnos", response_class=HTMLResponse)
def pagina_turnos() -> str:
    return pagina(
        "Turnos de cosecha",
        """<main><p class="muted">Productores</p><h1>Pedí un turno</h1>
        <div class="panel"><p>Este enlace se abre desde WhatsApp y vence en 10 minutos.</p>
        <p class="muted">La bodega debe definir primero la capacidad de cada sede.</p></div></main>""",
    )


@app.get("/fila-manifest.json")
def manifest() -> Response:
    return Response(MANIFEST, media_type="application/manifest+json")


@app.get("/fila-sw.js")
def service_worker() -> Response:
    return Response(SERVICE_WORKER, media_type="application/javascript")


@app.get("/api/publico/vehiculos/{patente}")
def vehiculo(patente: str, request: Request, repositorio: PublicoRepoDep):
    ip = request.client.host if request.client else "desconocida"
    try:
        dato = repositorio.autocompletar(patente, ip)
    except PatenteInvalida as exc:
        raise HTTPException(422, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(429, str(exc)) from exc
    if not dato:
        raise HTTPException(404, "camión no conocido")
    return dato


@app.post("/api/publico/viajes", status_code=201)
def alta_publica(
    alta: AltaPublica,
    request: Request,
    repositorio: PublicoRepoDep,
):
    ip = request.client.host if request.client else "desconocida"
    try:
        return repositorio.alta_publica(**alta.model_dump(), ip=ip)
    except PatenteInvalida as exc:
        raise HTTPException(422, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(429, str(exc)) from exc
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, "esa patente ya tiene un viaje activo") from exc


@app.get("/api/publico/tickets/{token}")
def estado_ticket(token: str, repositorio: PublicoRepoDep):
    dato = repositorio.ticket(token)
    if not dato:
        raise HTTPException(404, "ticket inexistente")
    return dato


@app.get("/api/guardia/{sede}")
def tablero_guardia(
    sede: str,
    _: Guardia,
    repositorio: GuardiaRepoDep,
):
    return repositorio.tablero(sede)


@app.post("/api/guardia/viajes/{viaje_id}/confirmar")
def confirmar(
    viaje_id: int,
    datos: Confirmacion,
    actor: Guardia,
    repositorio: GuardiaRepoDep,
):
    try:
        return repositorio.confirmar(viaje_id, actor=actor, **datos.model_dump())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/guardia/viajes/directo")
def alta_directa(
    datos: AltaGuardia,
    actor: Guardia,
    repositorio: GuardiaRepoDep,
):
    try:
        return repositorio.alta_directa(datos.model_dump(), actor)
    except (ValueError, psycopg.errors.UniqueViolation) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/guardia/viajes/{viaje_id}/{accion}")
def accionar(
    viaje_id: int,
    accion: str,
    datos: Accion,
    actor: Guardia,
    repositorio: GuardiaRepoDep,
):
    if accion not in {"llamar", "paso", "no_vino"}:
        raise HTTPException(404)
    try:
        return repositorio.accionar(
            viaje_id, accion, actor=actor, **datos.model_dump()
        )
    except (ValueError, LookupError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/pantalla/{sede}")
def datos_pantalla(
    sede: str,
    repositorio: GuardiaRepoDep,
    token: str | None = None,
):
    if token != os.environ.get("FILA_PANTALLA_TOKEN", ""):
        raise HTTPException(404)
    tablero = repositorio.tablero(sede)
    return {"llamados": tablero["llamados"]}


@app.post("/api/turnos", status_code=201)
def reservar_turno(
    pedido: PedidoTurno,
    repositorio: TurnosRepoDep,
    x_turnos_token: str | None = Header(default=None),
):
    if x_turnos_token != os.environ.get("FILA_TURNOS_TOKEN", ""):
        raise HTTPException(403)
    try:
        return repositorio.reservar_turno(pedido.model_dump())
    except SinCupo as exc:
        raise HTTPException(409, {"error": "sin_cupo", "disponibles_kg": exc.disponibles}) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
