from __future__ import annotations

import base64
from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import SesionActual, exigir_permiso

from ..application.lector_certificados import analizar_certificado
from ..application.servicios import GestionarSalud
from ..domain.modelos import (
    MARCA_SIMULADA,
    AccesoSaludDenegado,
    FuenteSimuladaEnProduccion,
    ReporteNominadoProhibido,
    Diagnostico,
)


class CertificadoEntrada(BaseModel):
    legajo: str = Field(min_length=1)
    diagnostico_codigo: str = Field(min_length=1)
    desde: date
    hasta: date
    dias: int = Field(gt=0)
    profesional: str = Field(min_length=1)
    adjunto_nombre: str = Field(min_length=1)
    adjunto_base64: str = Field(min_length=1)
    resumen: str = ""
    tipo_accidente: str = "NO_INFORMADO"


class AdjuntoEntrada(BaseModel):
    adjunto_nombre: str = Field(min_length=1)
    adjunto_base64: str = Field(min_length=1)


class DiagnosticoEntrada(BaseModel):
    codigo: str = Field(min_length=2, max_length=50)
    descripcion: str = Field(min_length=2, max_length=160)
    padre_codigo: str | None = None


def tabla_de_errores() -> list[tuple[type[BaseException], int]]:
    return [
        (AccesoSaludDenegado, 403),
        (ReporteNominadoProhibido, 400),
        (FuenteSimuladaEnProduccion, 503),
    ]


def crear_router(servicio: GestionarSalud, entorno: str = "prueba") -> APIRouter:
    if entorno.lower() == "produccion" and servicio.catalogo.simulada:
        raise FuenteSimuladaEnProduccion("Salud no arranca en producción con catálogo simulado.")
    app = APIRouter()
    leer = exigir_permiso("salud.diagnostico.leer")
    gestionar = exigir_permiso("salud.certificado.gestionar")

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(leer)])
    def pantalla() -> str:
        marca = f'<div class="simulada">{MARCA_SIMULADA}</div>' if servicio.catalogo.simulada else ""
        return (
            "<style>.simulada{background:#b00020;color:white;padding:16px;font-weight:bold}"
            "@media print{.simulada{display:block}}</style>"
            f"{marca}<h1>Salud laboral</h1><p>Acceso exclusivo del servicio médico.</p>"
        )

    @app.get("/catalogo", dependencies=[Depends(leer)])
    def catalogo(sesion: SesionActual):
        servicio.auditar(sesion.actor, None, "CONSULTA_CATALOGO")
        return {
            "items": [asdict(x) for x in servicio.catalogo.listar()],
            "fuente_simulada": servicio.catalogo.simulada,
            "dueno_dato": servicio.catalogo.dueno_dato,
        }

    @app.post("/catalogo", dependencies=[Depends(gestionar)])
    def crear_diagnostico(entrada: DiagnosticoEntrada, sesion: SesionActual):
        codigo = entrada.codigo.strip().upper()
        if servicio.catalogo.obtener(codigo):
            raise HTTPException(409, "Ya existe un diagnóstico con ese código.")
        return _guardar_diagnostico(entrada, codigo, sesion)

    @app.put("/catalogo/{codigo}", dependencies=[Depends(gestionar)])
    def editar_diagnostico(codigo: str, entrada: DiagnosticoEntrada, sesion: SesionActual):
        codigo = codigo.strip().upper()
        if servicio.catalogo.obtener(codigo) is None:
            raise HTTPException(404, "Diagnóstico inexistente.")
        return _guardar_diagnostico(entrada, codigo, sesion)

    def _guardar_diagnostico(entrada: DiagnosticoEntrada, codigo: str, sesion: SesionActual):
        padre = entrada.padre_codigo.strip().upper() if entrada.padre_codigo else None
        if padre == codigo:
            raise HTTPException(400, "Un diagnóstico no puede ser su propia categoría.")
        if padre and servicio.catalogo.obtener(padre) is None:
            raise HTTPException(400, "La categoría elegida no existe.")
        diagnostico = Diagnostico(codigo, entrada.descripcion.strip(), padre)
        servicio.catalogo.guardar(diagnostico)
        servicio.auditar(sesion.actor, None, "GESTION_CATALOGO_DIAGNOSTICOS")
        return asdict(diagnostico)

    @app.delete("/catalogo/{codigo}", dependencies=[Depends(gestionar)])
    def eliminar_diagnostico(codigo: str, sesion: SesionActual):
        try:
            servicio.catalogo.eliminar(codigo.strip().upper())
            servicio.auditar(sesion.actor, None, "GESTION_CATALOGO_DIAGNOSTICOS")
            return {"eliminado": True}
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/personas", dependencies=[Depends(leer)])
    def buscar_personas(q: str, sesion: SesionActual):
        servicio.auditar(sesion.actor, None, "BUSQUEDA_PERSONA")
        return [asdict(x) for x in servicio.buscar_personas(q)]

    @app.post("/certificados/analizar", dependencies=[Depends(gestionar)])
    def analizar(entrada: AdjuntoEntrada, sesion: SesionActual):
        try:
            contenido = base64.b64decode(entrada.adjunto_base64, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise HTTPException(400, "El archivo recibido no es válido.") from exc
        servicio.auditar(sesion.actor, None, "ANALISIS_CERTIFICADO")
        try:
            return analizar_certificado(entrada.adjunto_nombre, contenido)
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.post("/certificados", dependencies=[Depends(gestionar)])
    def cargar(entrada: CertificadoEntrada, sesion: SesionActual):
        try:
            contenido = base64.b64decode(entrada.adjunto_base64, validate=True)
            certificado = servicio.cargar(
                entrada.legajo, entrada.diagnostico_codigo, entrada.desde, entrada.hasta,
                entrada.dias, entrada.profesional, entrada.adjunto_nombre, contenido,
                entrada.resumen, entrada.tipo_accidente,
            )
            servicio.auditar(sesion.actor, entrada.legajo, "CARGA_CERTIFICADO")
            return asdict(certificado)
        except (ValueError, base64.binascii.Error) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/certificados", dependencies=[Depends(leer)])
    def listar_certificados(
        sesion: SesionActual, legajo: str | None = None,
        desde: date | None = None, hasta: date | None = None,
    ):
        return [asdict(x) for x in servicio.listar_certificados(
            sesion.actor, legajo=legajo, desde=desde, hasta=hasta
        )]

    @app.get("/certificados/{certificado_id}", dependencies=[Depends(leer)])
    def consultar(certificado_id: str, sesion: SesionActual):
        try:
            return asdict(servicio.consultar(certificado_id, sesion.actor, "MEDICO"))
        except AccesoSaludDenegado as exc:
            raise HTTPException(403, str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/certificados/{certificado_id}/adjunto", dependencies=[Depends(leer)])
    def consultar_adjunto(certificado_id: str, sesion: SesionActual):
        certificado = servicio.repositorio.obtener(certificado_id)
        if certificado is None:
            raise HTTPException(404, "Certificado inexistente.")
        adjunto = servicio.adjuntos.obtener(certificado.adjunto_id)
        if adjunto is None:
            raise HTTPException(404, "Adjunto inexistente.")
        servicio.auditar(sesion.actor, certificado.legajo, "CONSULTA_ADJUNTO")
        return {"nombre": adjunto.nombre, "contenido_base64": base64.b64encode(adjunto.contenido).decode()}

    @app.get("/reportes", dependencies=[Depends(leer)])
    def reporte(sesion: SesionActual, nominado: bool = False):
        try:
            resultado = servicio.reporte_agregado(nominado)
            servicio.auditar(sesion.actor, None, "CONSULTA_REPORTE_AGREGADO")
            return resultado
        except ReporteNominadoProhibido as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/bitacora", dependencies=[Depends(leer)])
    def bitacora(
        sesion: SesionActual, usuario: str | None = None, legajo: str | None = None,
        desde: date | None = None, hasta: date | None = None,
    ):
        return [asdict(x) for x in servicio.bitacora(
            sesion.actor, usuario=usuario, legajo=legajo, desde=desde, hasta=hasta
        )]

    @app.patch("/bitacora/{consulta_id}", dependencies=[Depends(leer)])
    @app.delete("/bitacora/{consulta_id}", dependencies=[Depends(leer)])
    def bitacora_inmutable(consulta_id: str):
        del consulta_id
        raise HTTPException(405, "La bitácora de Salud es inmutable.")

    @app.get("/articulo-208", dependencies=[Depends(leer)])
    def articulo_208(legajo: str, sesion: SesionActual):
        try:
            resultado = servicio.aviso_articulo_208(legajo)
            servicio.auditar(sesion.actor, legajo, "CONSULTA_ARTICULO_208")
            return resultado
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/articulo-208/{legajo}/imprimir", dependencies=[Depends(leer)])
    @app.get("/articulo-208/{legajo}/exportar", dependencies=[Depends(leer)])
    def bloquear_salida_preliminar(legajo: str):
        resultado = servicio.aviso_articulo_208(legajo)
        if resultado["preliminar"]:
            raise HTTPException(409, "El cálculo preliminar no se puede imprimir ni exportar.")
        return resultado

    return app


def crear_app(servicio: GestionarSalud, entorno: str = "prueba") -> FastAPI:
    app = FastAPI(title="Salud laboral")
    app.include_router(crear_router(servicio, entorno))
    return app
