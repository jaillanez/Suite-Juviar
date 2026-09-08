from __future__ import annotations

from dataclasses import asdict
from datetime import date
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import (
    exigir_identidad_configurada,
    exigir_permiso,
)

from ..application.servicios import AnularAsistencia, ReportesCapacitacion, planilla_imprimible
from ..domain.modelos import Asistencia, Dictado, Participante, Tema
from ..infrastructure.memoria import CapacitacionEnMemoria


class TemaEntrada(BaseModel):
    nombre: str = Field(min_length=1)
    horas: float = Field(gt=0)


class DictadoEntrada(BaseModel):
    tema_id: str
    fecha: date
    instructor: str = Field(min_length=1)


class AsistenciaEntrada(BaseModel):
    legajo: str
    nombre_completo: str
    presente: bool
    supervisor: bool = False


class AnulacionEntrada(BaseModel):
    motivo: str = Field(min_length=1)
    actor: str = Field(min_length=1)


def crear_app(configuracion, entorno: str = "prueba") -> FastAPI:
    exigir_identidad_configurada(entorno)
    app = FastAPI(
        title="Capacitaciones",
        dependencies=[Depends(exigir_permiso("capacitacion.gestionar"))],
    )
    repo = CapacitacionEnMemoria()
    reportes = ReportesCapacitacion(repo, configuracion)
    anular = AnularAsistencia(repo)

    @app.get("/temas")
    def temas():
        return [{**asdict(t), "dictados": [asdict(d) for d in repo.dictados_del_tema(t.id)]}
                for t in repo.temas.values()]

    @app.post("/temas", status_code=201)
    def crear_tema(entrada: TemaEntrada):
        tema = Tema(str(uuid4()), entrada.nombre, entrada.horas)
        repo.guardar_tema(tema)
        return tema

    @app.post("/dictados", status_code=201)
    def crear_dictado(entrada: DictadoEntrada):
        try:
            dictado = Dictado(str(uuid4()), entrada.tema_id, entrada.fecha, entrada.instructor)
            repo.guardar_dictado(dictado)
            return dictado
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/dictados/{dictado_id}/asistencias")
    def asistencias(dictado_id: str):
        return repo.asistencias_del_dictado(dictado_id)

    @app.post("/dictados/{dictado_id}/asistencias", status_code=201)
    def tomar_asistencia(dictado_id: str, entrada: AsistenciaEntrada):
        if repo.obtener_dictado(dictado_id) is None:
            raise HTTPException(404, "Dictado inexistente")
        asistencia = Asistencia(dictado_id, Participante(entrada.legajo,
            entrada.nombre_completo, entrada.supervisor), entrada.presente, None,
            "PENDIENTE_FIRMA_PAPEL" if entrada.presente else "AUSENTE")
        repo.guardar_asistencia(asistencia)
        return asistencia

    @app.post("/dictados/{dictado_id}/asistencias/{legajo}/anular")
    def anular_registro(dictado_id: str, legajo: str, entrada: AnulacionEntrada):
        try:
            return anular.ejecutar(dictado_id, legajo, entrada.motivo, entrada.actor)
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
            "porcentaje_tema": reportes.porcentaje_tema(tema_id) if tema_id else None,
            "porcentaje_persona": reportes.porcentaje_persona(legajo) if legajo else None,
            "horas_persona": reportes.horas_por_persona(legajo, anio) if legajo and anio else None,
            "supervisores_baja_asistencia": reportes.alertas_supervisores(),
            "configuracion": configuracion.estado,
        }

    return app
