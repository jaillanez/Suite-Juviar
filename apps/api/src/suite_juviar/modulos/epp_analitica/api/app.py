from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import Response

from suite_juviar.plataforma.identidad.api.dependencias import exigir_permiso

from ..application.servicios import AnalizarEPP
from ..domain.modelos import MARCA_SIMULADA, ExportacionNoPermitida, FuenteSimuladaEnProduccion


def crear_app(servicio: AnalizarEPP, entorno: str = "prueba") -> FastAPI:
    if entorno.lower() == "produccion" and servicio.datos_simulados:
        raise FuenteSimuladaEnProduccion(
            "Analítica EPP no arranca en producción con fuentes simuladas."
        )
    app = FastAPI(
        title="Analítica EPP para Compras",
        dependencies=[Depends(exigir_permiso("epp.analitica.leer"))],
    )

    @app.get("/")
    @app.get("/tablero")
    def pantalla(desde: date, hasta: date, sector: str | None = None, puesto: str | None = None):
        metricas = servicio.metricas(desde, hasta)
        if sector:
            metricas = [m for m in metricas if m.sector == sector]
        if puesto:
            metricas = [m for m in metricas if m.puesto == puesto]
        return {
            "metricas": [asdict(m) for m in metricas],
            "fecha_corte": hasta.isoformat(),
            "desde": desde.isoformat(),
            "hasta": hasta.isoformat(),
            "datos_simulados": servicio.datos_simulados,
            "marca": MARCA_SIMULADA if servicio.datos_simulados else None,
            "costo": None,
            "costo_leyenda": "Faltan precios reales de Compras",
            "exportacion": {
                "habilitada": not servicio.datos_simulados,
                "motivo": "Hay entregas contra ítems SIM-*" if servicio.datos_simulados else None,
            },
        }

    @app.get("/comparador")
    def comparador(item_a: str, item_b: str, desde: date, hasta: date):
        try:
            return servicio.comparar(item_a, item_b, desde, hasta)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/exportar")
    def exportar(desde: date, hasta: date) -> Response:
        try:
            contenido = servicio.exportar(desde, hasta)
        except ExportacionNoPermitida as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return Response(contenido, media_type="text/csv")

    return app
