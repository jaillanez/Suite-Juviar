from __future__ import annotations

from datetime import date

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

from suite_juviar.plataforma.identidad.api.dependencias import exigir_permiso

from ..application.servicios import AnalizarEPP
from ..domain.modelos import MARCA_SIMULADA, ExportacionNoPermitida, FuenteSimuladaEnProduccion


def crear_app(servicio: AnalizarEPP, entorno: str = "prueba") -> FastAPI:
    if entorno.lower() == "produccion" and servicio.datos_simulados:
        raise FuenteSimuladaEnProduccion("Analítica EPP no arranca en producción con fuentes simuladas.")
    app = FastAPI(
        title="Analítica EPP para Compras",
        dependencies=[Depends(exigir_permiso("epp.analitica.leer"))],
    )

    @app.get("/", response_class=HTMLResponse)
    def pantalla(desde: date, hasta: date) -> str:
        marca = f'<div class="simulada">{MARCA_SIMULADA}</div>' if servicio.datos_simulados else ""
        filas = "".join(
            f"<tr><td>{m.item_codigo}</td><td>{m.sector}</td><td>{m.puesto}</td>"
            f"<td>{m.consumo}</td><td>{m.estado_duracion}</td></tr>"
            for m in servicio.metricas(desde, hasta)
        )
        return (
            "<style>.simulada{background:#b00020;color:white;padding:16px;font-weight:bold}"
            "@media print{.simulada{display:block}}</style>"
            f"{marca}<h1>Analítica EPP para Compras</h1>"
            "<p>Los costos quedan vacíos hasta recibir precios reales de Compras.</p>"
            "<table><tr><th>Ítem</th><th>Sector</th><th>Puesto</th>"
            f"<th>Consumo</th><th>Duración</th></tr>{filas}</table>"
        )

    @app.get("/exportar")
    def exportar(desde: date, hasta: date) -> Response:
        try:
            contenido = servicio.exportar(desde, hasta)
        except ExportacionNoPermitida as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return Response(contenido, media_type="text/csv")

    return app
