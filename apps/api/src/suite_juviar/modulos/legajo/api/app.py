from __future__ import annotations

from base64 import b64decode, b64encode

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import exigir_permiso

from ..application.servicios import GestionarLegajo
from ..domain.modelos import MARCA_SIMULADA, FuenteSimuladaEnProduccion


class AdjuntoEntrada(BaseModel):
    legajo: str = Field(min_length=1)
    nombre: str = Field(min_length=1)
    contenido_base64: str = Field(min_length=1)


def crear_app(servicio: GestionarLegajo, entorno: str = "prueba") -> FastAPI:
    if entorno.lower() == "produccion" and servicio.legajos.simulada:
        raise FuenteSimuladaEnProduccion("Legajo no arranca en producción con Nexus simulado.")
    app = FastAPI(
        title="Legajo digital", dependencies=[Depends(exigir_permiso("legajo.leer"))]
    )

    @app.get("/{legajo}", response_class=HTMLResponse)
    def ficha(legajo: str) -> str:
        datos = servicio.ficha(legajo)
        if datos is None:
            raise HTTPException(404, "Legajo inexistente")
        marca = f'<div class="simulada">{MARCA_SIMULADA}</div>' if servicio.legajos.simulada else ""
        return (
            "<style>.simulada{background:#b00020;color:#fff;padding:16px;font-weight:bold}"
            "@media print{.simulada{display:block}}</style>"
            f"{marca}<h1>{datos['formato']}</h1><p>{datos['nombre_completo']}</p>"
        )

    @app.post("/adjuntos")
    def adjuntar(entrada: AdjuntoEntrada) -> dict[str, str]:
        try:
            adjunto = servicio.adjuntar(
                entrada.legajo, entrada.nombre, b64decode(entrada.contenido_base64, validate=True)
            )
        except (LookupError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"id": adjunto.id, "legajo": adjunto.legajo, "nombre": adjunto.nombre}

    @app.get("/adjuntos/{adjunto_id}")
    def obtener_adjunto(adjunto_id: str) -> dict[str, str]:
        adjunto = servicio.adjuntos.obtener(adjunto_id)
        if adjunto is None:
            raise HTTPException(404, "Adjunto inexistente")
        return {
            "id": adjunto.id,
            "nombre": adjunto.nombre,
            "contenido_base64": b64encode(adjunto.contenido).decode(),
            "marca": MARCA_SIMULADA if servicio.legajos.simulada else "DATOS REALES",
        }

    return app
