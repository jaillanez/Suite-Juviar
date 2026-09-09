from __future__ import annotations

from base64 import b64decode, b64encode
from dataclasses import asdict

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import SesionActual, exigir_permiso

from ..application.servicios import GestionarLegajo
from ..domain.modelos import MARCA_SIMULADA, FuenteSimuladaEnProduccion


class AdjuntoEntrada(BaseModel):
    legajo: str = Field(min_length=1)
    nombre: str = Field(min_length=1)
    contenido_base64: str = Field(min_length=1)


class BajaAdjuntoEntrada(BaseModel):
    motivo: str = Field(min_length=1)


def crear_app(servicio: GestionarLegajo, entorno: str = "prueba") -> FastAPI:
    if entorno.lower() == "produccion" and servicio.legajos.simulada:
        raise FuenteSimuladaEnProduccion("Legajo no arranca en producción con Nexus simulado.")
    app = FastAPI(title="Legajo digital")

    @app.get("/personas", dependencies=[Depends(exigir_permiso("legajo.leer"))])
    def buscar(apellido: str | None = None, legajo: str | None = None,
               sector: str | None = None, empresa: str | None = None):
        return [asdict(p) for p in servicio.buscar(
            apellido=apellido, legajo=legajo, sector=sector, empresa=empresa
        )]

    @app.get("/personas/{legajo}", dependencies=[Depends(exigir_permiso("legajo.leer"))])
    def ficha(legajo: str):
        datos = servicio.ficha(legajo)
        if datos is None:
            raise HTTPException(404, "Legajo inexistente")
        return {**datos, "fuente_simulada": servicio.legajos.simulada,
                "marca": MARCA_SIMULADA if servicio.legajos.simulada else None}

    @app.get("/personas/{legajo}/formato", response_class=HTMLResponse,
             dependencies=[Depends(exigir_permiso("legajo.leer"))])
    def formato(legajo: str) -> str:
        datos = servicio.ficha(legajo)
        if datos is None:
            raise HTTPException(404, "Legajo inexistente")
        marca = f'<div class="simulada">{MARCA_SIMULADA}</div>' if servicio.legajos.simulada else ""
        titulo = "Ficha de personal ENAV" if datos["formato"] == "FICHA_ENAV" else "Ficha de personal Jubiar"
        return (
            "<style>.simulada{background:#b00020;color:#fff;padding:16px;font-weight:bold}"
            "@media print{.simulada{display:block}}</style>"
            f"{marca}<h1>{titulo}</h1><p>{datos['nombre_completo']}</p>"
            f"<p>Legajo {datos['legajo']} · {datos['empresa']} · {datos['sector']} · {datos['puesto']}</p>"
            "<p>Datos provenientes de Nexus · sólo lectura</p>"
        )

    @app.post("/adjuntos", dependencies=[Depends(exigir_permiso("legajo.adjuntos.gestionar"))])
    def adjuntar(entrada: AdjuntoEntrada) -> dict[str, str]:
        try:
            adjunto = servicio.adjuntar(
                entrada.legajo, entrada.nombre, b64decode(entrada.contenido_base64, validate=True)
            )
        except (LookupError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"id": adjunto.id, "legajo": adjunto.legajo, "nombre": adjunto.nombre}

    @app.get("/personas/{legajo}/adjuntos", dependencies=[Depends(exigir_permiso("legajo.leer"))])
    def listar_adjuntos(legajo: str):
        return [{"id": a.id, "legajo": a.legajo, "nombre": a.nombre, "activo": a.activo,
                 "motivo_baja": a.motivo_baja, "dado_baja_por": a.dado_baja_por,
                 "dado_baja_en": a.dado_baja_en} for a in servicio.adjuntos.listar(legajo)]

    @app.get("/adjuntos/{adjunto_id}", dependencies=[Depends(exigir_permiso("legajo.leer"))])
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

    @app.post("/adjuntos/{adjunto_id}/baja",
              dependencies=[Depends(exigir_permiso("legajo.adjuntos.gestionar"))])
    def baja_adjunto(adjunto_id: str, entrada: BajaAdjuntoEntrada, sesion: SesionActual):
        try:
            a = servicio.baja_adjunto(adjunto_id, entrada.motivo, sesion.actor)
            return {"id": a.id, "activo": a.activo, "motivo_baja": a.motivo_baja,
                    "dado_baja_por": a.dado_baja_por, "dado_baja_en": a.dado_baja_en}
        except (LookupError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

    return app
