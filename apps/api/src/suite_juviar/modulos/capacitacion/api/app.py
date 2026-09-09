from __future__ import annotations

import base64
from dataclasses import asdict
from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from suite_juviar.plataforma.firma.domain.entidades import MetodoFirmaElectronica
from suite_juviar.plataforma.firma.infrastructure.simulada import MotorFirmaSimulado
from suite_juviar.plataforma.identidad.api.dependencias import (
    SesionActual,
    exigir_identidad_configurada,
    exigir_permiso,
)

from ..application.importacion_historica import ImportacionesHistoricas
from ..application.servicios import (
    AnularAsistencia,
    RegistrarAsistencia,
    ReportesCapacitacion,
    planilla_imprimible,
)
from ..domain.modelos import Dictado, Participante, Tema
from ..infrastructure.memoria import CapacitacionEnMemoria


class TemaEntrada(BaseModel):
    nombre: str = Field(min_length=1)
    horas: float = Field(gt=0)
    periodicidad_meses: int | None = Field(default=None, gt=0)


class DictadoEntrada(BaseModel):
    tema_id: str
    fecha: date
    instructor: str = Field(min_length=1)
    duracion_horas: float = Field(default=1, gt=0)
    convocatoria_tipo: str | None = None
    convocatoria_detalle: str | None = None
    convocados: list[str] = []


class AsistenciaEntrada(BaseModel):
    legajo: str
    nombre_completo: str
    presente: bool
    supervisor: bool = False
    metodo_firma: str | None = None
    evidencia_firma: str | None = None


class AnulacionEntrada(BaseModel):
    motivo: str = Field(min_length=1)


class ImportacionEntrada(BaseModel):
    contenido_base64: str


def crear_app(configuracion, entorno: str = "prueba") -> FastAPI:
    exigir_identidad_configurada(entorno)
    app = FastAPI(
        title="Capacitaciones",
        dependencies=[Depends(exigir_permiso("capacitacion.gestionar"))],
    )
    repo = CapacitacionEnMemoria()
    reportes = ReportesCapacitacion(repo, configuracion)
    anular = AnularAsistencia(repo)
    registrar = RegistrarAsistencia(repo, MotorFirmaSimulado())
    importaciones = ImportacionesHistoricas(repo)

    @app.get("/temas")
    def temas():
        return [
            {**asdict(t), "dictados": [asdict(d) for d in repo.dictados_del_tema(t.id)]}
            for t in repo.temas.values()
        ]

    @app.post("/temas", status_code=201)
    def crear_tema(entrada: TemaEntrada):
        tema = Tema(str(uuid4()), entrada.nombre, entrada.horas, entrada.periodicidad_meses)
        repo.guardar_tema(tema)
        return tema

    @app.post("/dictados", status_code=201)
    def crear_dictado(entrada: DictadoEntrada):
        try:
            dictado = Dictado(
                str(uuid4()),
                entrada.tema_id,
                entrada.fecha,
                entrada.instructor,
                entrada.duracion_horas,
                entrada.convocatoria_tipo,
                entrada.convocatoria_detalle,
                tuple(dict.fromkeys(entrada.convocados)),
            )
            repo.guardar_dictado(dictado)
            return dictado
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/dictados/{dictado_id}/asistencias")
    def asistencias(dictado_id: str):
        return [
            {
                **asdict(a),
                "anulada": anulacion is not None,
                "anulacion": asdict(anulacion) if anulacion else None,
            }
            for a, anulacion in repo.asistencias_del_dictado_con_anuladas(dictado_id)
        ]

    @app.post("/dictados/{dictado_id}/asistencias", status_code=201)
    async def tomar_asistencia(dictado_id: str, entrada: AsistenciaEntrada):
        if repo.obtener_dictado(dictado_id) is None:
            raise HTTPException(404, "Dictado inexistente")
        metodo = MetodoFirmaElectronica(entrada.metodo_firma) if entrada.metodo_firma else None
        try:
            return await registrar.ejecutar(
                dictado_id,
                Participante(entrada.legajo, entrada.nombre_completo, entrada.supervisor),
                entrada.presente,
                metodo,
                entrada.evidencia_firma.encode() if entrada.evidencia_firma else None,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/dictados/{dictado_id}/asistencias/{legajo}/anular")
    def anular_registro(
        dictado_id: str, legajo: str, entrada: AnulacionEntrada, sesion: SesionActual
    ):
        try:
            return anular.ejecutar(dictado_id, legajo, entrada.motivo, sesion.actor)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/dictados/{dictado_id}/planilla", response_class=PlainTextResponse)
    def planilla(dictado_id: str):
        dictado = repo.obtener_dictado(dictado_id)
        if dictado is None:
            raise HTTPException(404, "Dictado inexistente")
        tema = repo.obtener_tema(dictado.tema_id)
        return planilla_imprimible(tema.nombre if tema else dictado.tema_id, dictado.fecha)

    @app.get("/reportes")
    def reporte(tema_id: str | None = None, legajo: str | None = None, anio: int | None = None):
        return {
            "tema": reportes.resumen_tema(tema_id) if tema_id else None,
            "porcentaje_persona": reportes.porcentaje_persona(legajo) if legajo else None,
            "horas_persona": reportes.horas_por_persona(legajo, anio) if legajo and anio else None,
            "supervisores_baja_asistencia": reportes.alertas_supervisores(),
            "recapacitaciones": reportes.recapacitaciones(),
            "configuracion": configuracion.estado,
            "fecha_corte": datetime.now(UTC).date().isoformat(),
        }

    @app.post("/historico/importaciones")
    def previsualizar_historico(entrada: ImportacionEntrada):
        try:
            return importaciones.previsualizar(
                base64.b64decode(entrada.contenido_base64, validate=True)
            )
        except (ValueError, base64.binascii.Error) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/historico/importaciones/{identificador}/aplicar")
    def aplicar_historico(identificador: str):
        try:
            return importaciones.aplicar(identificador)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    return app
