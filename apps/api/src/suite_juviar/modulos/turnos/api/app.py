from __future__ import annotations

from dataclasses import asdict
from datetime import date, time
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import SesionActual, exigir_permiso

from ..application.servicios import ConciliarTurnos
from ..domain.entidades import EstadoImputacion, FuenteSimuladaEnProduccion


class CronogramaEntrada(BaseModel):
    legajo: str = Field(min_length=1)
    sector: str = Field(min_length=1)
    fecha: date
    desde: time
    hasta: time


class AsignacionEntrada(BaseModel):
    legajo: str = Field(min_length=1)
    fecha: date
    desde: time
    hasta: time


class SemanaEntrada(BaseModel):
    sector: str = Field(min_length=1)
    asignaciones: list[AsignacionEntrada] = Field(min_length=1)


class CambioTardioEntrada(BaseModel):
    desde: time
    hasta: time


class ResolucionLoteEntrada(BaseModel):
    ids: list[str] = Field(min_length=1)
    accion: str = Field(pattern="^(APROBAR|RECHAZAR|CAMBIAR)$")
    motivo_cambio: str | None = None


SectorSimulado = Annotated[str, Header(alias="X-Sector-Simulado")]


def crear_app(servicio: ConciliarTurnos, entorno: str = "prueba") -> FastAPI:
    if entorno.lower() == "produccion" and servicio.simulada:
        raise FuenteSimuladaEnProduccion("Turnos no arranca en producción con fichadas simuladas.")
    app = FastAPI(title="Conciliación de turnos")
    leer = exigir_permiso("turnos.cronograma.leer")
    editar = exigir_permiso("turnos.cronograma.editar")
    aprobar = exigir_permiso("turnos.imputacion.aprobar")

    def sector_habilitado(sesion, pedido: str | None, propio: str) -> str | None:
        es_supervisor = sesion.puede("turnos.cronograma.editar") and not sesion.puede(
            "turnos.imputacion.aprobar")
        if es_supervisor and pedido and pedido.casefold() != propio.casefold():
            raise HTTPException(403, "El supervisor sólo puede operar su sector.")
        return propio if es_supervisor else pedido

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(leer)])
    def pantalla() -> str:
        marca = '<div class="simulada">DATOS SIMULADOS — SIN VALIDEZ</div>' if servicio.simulada else ""
        return (
            "<style>.simulada{background:#b00020;color:white;padding:16px;font-weight:bold}"
            "@media print{.simulada{display:block}}</style>"
            f"{marca}<h1>Conciliación de turnos</h1>"
            "<p>Las imputaciones son propuestas hasta la aprobación expresa de RRHH.</p>"
        )

    @app.get("/cronogramas", dependencies=[Depends(leer)])
    def listar_cronogramas(sesion: SesionActual, sector_propio: SectorSimulado = "Bodega",
                           sector: str | None = None, desde: date | None = None,
                           hasta: date | None = None):
        alcance = sector_habilitado(sesion, sector, sector_propio)
        return [asdict(x) for x in servicio.listar_cronogramas(
            sector=alcance, desde=desde, hasta=hasta)]

    @app.post("/cronogramas", dependencies=[Depends(editar)])
    def cargar(entrada: CronogramaEntrada, sesion: SesionActual,
               sector_propio: SectorSimulado = "Bodega"):
        sector_habilitado(sesion, entrada.sector, sector_propio)
        try:
            return asdict(servicio.cargar_cronograma(
                entrada.legajo, entrada.sector, entrada.fecha,
                entrada.desde, entrada.hasta, sesion.actor))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/cronogramas/semana", dependencies=[Depends(editar)])
    def cargar_semana(entrada: SemanaEntrada, sesion: SesionActual,
                      sector_propio: SectorSimulado = "Bodega"):
        sector_habilitado(sesion, entrada.sector, sector_propio)
        try:
            filas = [x.model_dump() for x in entrada.asignaciones]
            return [asdict(x) for x in servicio.cargar_semana(entrada.sector, filas, sesion.actor)]
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/cronogramas/{cronograma_id}/cambio-tardio", dependencies=[Depends(editar)])
    def cambio_tardio(cronograma_id: str, entrada: CambioTardioEntrada,
                      sesion: SesionActual, sector_propio: SectorSimulado = "Bodega"):
        plan = next((x for x in servicio.cronogramas if str(x.id) == cronograma_id), None)
        if plan is None:
            raise HTTPException(404, "Cronograma inexistente.")
        sector_habilitado(sesion, plan.sector, sector_propio)
        try:
            return asdict(servicio.registrar_cambio_tardio(
                cronograma_id, entrada.desde, entrada.hasta,
                sesion.actor))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/cronogramas/historial", dependencies=[Depends(leer)])
    def historial(sesion: SesionActual, sector_propio: SectorSimulado = "Bodega",
                  sector: str | None = None):
        alcance = sector_habilitado(sesion, sector, sector_propio)
        return [asdict(x) for x in servicio.historial(sector=alcance)]

    @app.get("/conciliacion", dependencies=[Depends(leer)])
    def conciliacion(sesion: SesionActual, desde: date, hasta: date,
                     sector_propio: SectorSimulado = "Bodega",
                     sector: str | None = None, legajo: str | None = None):
        alcance = sector_habilitado(sesion, sector, sector_propio)
        return [asdict(x) for x in servicio.conciliar(
            desde, hasta, sector=alcance, legajo=legajo)]

    @app.post("/conciliar", dependencies=[Depends(leer)])
    def conciliar_compatible(sesion: SesionActual, desde: date, hasta: date):
        return [asdict(x) for x in servicio.conciliar(desde, hasta)]

    @app.get("/propuestas", dependencies=[Depends(leer)])
    def propuestas(estado: EstadoImputacion | None = None):
        return [{**asdict(x), "antiguedad_dias": servicio.antiguedad_pendiente(x)}
                for x in servicio.listar_propuestas(estado=estado)]

    @app.post("/propuestas/resolver-lote", dependencies=[Depends(aprobar)])
    def resolver(entrada: ResolucionLoteEntrada, sesion: SesionActual):
        try:
            salida = servicio.resolver_lote(
                entrada.ids, entrada.accion, sesion.actor, entrada.motivo_cambio)
            return {"resueltas": len(entrada.ids), "salida": asdict(salida) if salida else None}
        except (ValueError, LookupError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/aprobar-lote", dependencies=[Depends(aprobar)])
    def aprobar_compatible(entrada: ResolucionLoteEntrada, sesion: SesionActual):
        return resolver(entrada, sesion)

    @app.get("/bandeja", dependencies=[Depends(aprobar)])
    def bandeja():
        return [asdict(x) for x in servicio.bandeja]

    @app.get("/reportes/regularizaciones-tardias", dependencies=[Depends(leer)])
    def reporte_tardias(desde: date, hasta: date):
        return servicio.reporte_tardias(desde, hasta)

    return app
