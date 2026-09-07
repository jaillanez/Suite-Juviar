from __future__ import annotations

from datetime import date, time

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..application.servicios import ConciliarTurnos
from ..domain.entidades import FuenteSimuladaEnProduccion


class CronogramaEntrada(BaseModel):
    legajo: str = Field(min_length=1)
    sector: str = Field(min_length=1)
    fecha: date
    desde: time
    hasta: time
    autor: str = Field(min_length=1)


class AprobacionEntrada(BaseModel):
    ids: list[str] = Field(min_length=1)
    actor_rrhh: str = Field(min_length=1)


def crear_app(servicio: ConciliarTurnos, entorno: str = "prueba") -> FastAPI:
    if entorno.lower() == "produccion" and servicio.simulada:
        raise FuenteSimuladaEnProduccion("Turnos no arranca en producción con fichadas simuladas.")
    app = FastAPI(title="Conciliación de turnos")

    @app.get("/", response_class=HTMLResponse)
    def pantalla() -> str:
        marca = '<div class="simulada">DATOS SIMULADOS — SIN VALIDEZ</div>' if servicio.simulada else ""
        return (
            "<style>.simulada{background:#b00020;color:white;padding:16px;font-weight:bold}"
            "@media print{.simulada{display:block}}</style>"
            f"{marca}<h1>Conciliación de turnos</h1>"
            "<p>Las imputaciones son propuestas hasta la aprobación expresa de RRHH.</p>"
        )

    @app.post("/cronogramas")
    def cargar(entrada: CronogramaEntrada):
        return servicio.cargar_cronograma(
            entrada.legajo,
            entrada.sector,
            entrada.fecha,
            entrada.desde,
            entrada.hasta,
            entrada.autor,
        )

    @app.post("/conciliar")
    def conciliar(desde: date, hasta: date):
        return servicio.conciliar(desde, hasta)

    @app.post("/aprobar-lote")
    def aprobar(entrada: AprobacionEntrada) -> dict[str, str]:
        return {"bandeja": servicio.aprobar_lote(entrada.ids, entrada.actor_rrhh)}

    return app
