from __future__ import annotations

from datetime import date

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..application.servicios import GestionarSalud
from ..domain.modelos import (
    MARCA_SIMULADA,
    AccesoSaludDenegado,
    FuenteSimuladaEnProduccion,
    ReporteNominadoProhibido,
)


class CertificadoEntrada(BaseModel):
    legajo: str = Field(min_length=1)
    diagnostico_codigo: str = Field(min_length=1)
    desde: date
    hasta: date


def crear_app(servicio: GestionarSalud, entorno: str = "prueba") -> FastAPI:
    if entorno.lower() == "produccion" and servicio.catalogo.simulada:
        raise FuenteSimuladaEnProduccion("Salud no arranca en producción con catálogo simulado.")
    app = FastAPI(title="Salud laboral")

    @app.get("/", response_class=HTMLResponse)
    def pantalla() -> str:
        marca = f'<div class="simulada">{MARCA_SIMULADA}</div>' if servicio.catalogo.simulada else ""
        return (
            "<style>.simulada{background:#b00020;color:white;padding:16px;font-weight:bold}"
            "@media print{.simulada{display:block}}</style>"
            f"{marca}<h1>Salud laboral</h1><p>Acceso exclusivo del servicio médico.</p>"
        )

    @app.get("/catalogo")
    def catalogo():
        return servicio.catalogo.listar()

    @app.post("/certificados")
    def cargar(
        entrada: CertificadoEntrada,
        x_rol: str | None = Header(default=None, alias="X-Rol"),
    ):
        if x_rol != "MEDICO":
            raise HTTPException(403, "La carga de diagnósticos requiere el rol médico.")
        try:
            return servicio.cargar(
                entrada.legajo, entrada.diagnostico_codigo, entrada.desde, entrada.hasta
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/certificados/{certificado_id}")
    def consultar(
        certificado_id: str,
        x_actor: str = Header(default="", alias="X-Actor"),
        x_rol: str | None = Header(default=None, alias="X-Rol"),
    ):
        try:
            return servicio.consultar(certificado_id, x_actor, x_rol)
        except AccesoSaludDenegado as exc:
            raise HTTPException(403, str(exc)) from exc

    @app.get("/reportes")
    def reporte(nominado: bool = False):
        try:
            return servicio.reporte_agregado(nominado)
        except ReporteNominadoProhibido as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/bitacora")
    def bitacora(x_rol: str | None = Header(default=None, alias="X-Rol")):
        if x_rol != "MEDICO":
            raise HTTPException(403, "La bitácora de salud requiere el rol médico.")
        return servicio.repositorio.consultas

    @app.get("/articulo-208")
    def articulo_208(antiguedad_dias: int, cargas_familia: int):
        return servicio.aviso_articulo_208(antiguedad_dias, cargas_familia, True)

    return app
