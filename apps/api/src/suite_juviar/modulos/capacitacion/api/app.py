from __future__ import annotations

import base64
from dataclasses import asdict
from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException
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
from ..application.planillas import PlanillasEscaneadas
from ..application.servicios import (
    AnularAsistencia,
    RegistrarAsistencia,
    ReportesCapacitacion,
    planilla_imprimible,
)
from ..domain.modelos import Dictado, FilaPlanilla, Participante, PlanillaEscaneada, Tema
from ..domain.puertos import LectorPlanillas, PadronPersonal
from ..infrastructure.lector_planillas import LectorPlanillasIA, usaria_ia_externa
from ..infrastructure.sqlite import CapacitacionSQLite


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


class PlanillaEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    contenido_base64: str = Field(min_length=1)


class FilaEntrada(BaseModel):
    legajo: str = Field(max_length=20)
    nombre_completo: str = Field(max_length=120)
    presente: bool | None


class AprobacionEntrada(BaseModel):
    filas: list[FilaEntrada] = Field(max_length=500)


class DescarteEntrada(BaseModel):
    motivo: str = Field(min_length=1, max_length=300)


def crear_router(
    configuracion,
    entorno: str = "prueba",
    ruta_base: str = "datos/modulos.sqlite3",
    padron: PadronPersonal | None = None,
    lector: LectorPlanillas | None = None,
) -> APIRouter:
    exigir_identidad_configurada(entorno)
    app = APIRouter(dependencies=[Depends(exigir_permiso("capacitacion.gestionar"))])
    repo = CapacitacionSQLite(ruta_base)
    reportes = ReportesCapacitacion(repo, configuracion)
    anular = AnularAsistencia(repo)
    registrar = RegistrarAsistencia(repo, MotorFirmaSimulado())
    importaciones = ImportacionesHistoricas(repo)
    planillas = PlanillasEscaneadas(repo, repo, lector or LectorPlanillasIA())

    def padron_para(sesion) -> PadronPersonal | None:
        """El padrón de personal sólo lo ve quien tiene acceso a legajos."""
        return padron if sesion.puede("legajo.leer") else None

    def esperados(dictado: Dictado, sesion) -> list[FilaPlanilla]:
        """Quienes van impresos en la planilla: los convocados y los ya anotados en el dictado."""
        fuente = padron_para(sesion)
        # Sólo personal activo: un legajo cargado a mano no destapa datos de una ficha.
        activos = {p.legajo: p for p in fuente.buscar()} if fuente else {}
        nombres = {a.participante.legajo: a.participante.nombre_completo
                   for a in repo.asistencias_del_dictado(dictado.id)}
        filas = []
        for legajo in dict.fromkeys([*dictado.convocados, *nombres]):
            persona = activos.get(legajo)
            filas.append(FilaPlanilla(legajo, persona.nombre_completo if persona else nombres.get(legajo, ""), None))
        return filas

    def vista_planilla(p: PlanillaEscaneada, con_archivo: bool = False) -> dict:
        dictado = repo.obtener_dictado(p.dictado_id)
        tema = repo.obtener_tema(dictado.tema_id) if dictado else None
        datos = {
            "id": p.id, "dictado_id": p.dictado_id, "tema": tema.nombre if tema else "",
            "fecha_dictado": dictado.fecha.isoformat() if dictado else None,
            "nombre_archivo": p.nombre_archivo, "cargada_en": p.cargada_en.isoformat(),
            "cargada_por": p.cargada_por, "estado": p.estado, "motor": p.motor, "mensaje": p.mensaje,
            "filas": [asdict(f) for f in p.filas], "revisada_por": p.revisada_por,
            "revisada_en": p.revisada_en.isoformat() if p.revisada_en else None,
            "motivo_descarte": p.motivo_descarte, "resultado": p.resultado,
        }
        if con_archivo:
            datos["contenido_base64"] = base64.b64encode(repo.archivo_planilla(p.id) or b"").decode()
        return datos

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
    def planilla(dictado_id: str, sesion: SesionActual):
        dictado = repo.obtener_dictado(dictado_id)
        if dictado is None:
            raise HTTPException(404, "Dictado inexistente")
        tema = repo.obtener_tema(dictado.tema_id)
        personas = [(f.legajo, f.nombre_completo) for f in esperados(dictado, sesion)]
        return planilla_imprimible(tema.nombre if tema else dictado.tema_id, dictado.fecha, personas)

    @app.get("/planillas-escaneadas/ia-externa")
    def ia_externa(nombre: str):
        return {"usaria_ia_externa": usaria_ia_externa(nombre)}

    @app.post("/dictados/{dictado_id}/planillas-escaneadas", status_code=201)
    def cargar_planilla(dictado_id: str, entrada: PlanillaEntrada, sesion: SesionActual):
        dictado = repo.obtener_dictado(dictado_id)
        if dictado is None:
            raise HTTPException(404, "Dictado inexistente")
        try:
            contenido = base64.b64decode(entrada.contenido_base64, validate=True)
            return vista_planilla(planillas.cargar(dictado_id, entrada.nombre, contenido, sesion.actor,
                                                   esperados(dictado, sesion)))
        except (ValueError, base64.binascii.Error) as exc:
            raise HTTPException(400, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.get("/planillas-escaneadas")
    def listar_planillas(estado: str | None = None):
        return [vista_planilla(p) for p in repo.listar_planillas() if not estado or p.estado == estado]

    @app.get("/planillas-escaneadas/{planilla_id}")
    def ver_planilla(planilla_id: str):
        planilla = repo.obtener_planilla(planilla_id)
        if planilla is None:
            raise HTTPException(404, "No existe la planilla")
        return vista_planilla(planilla, con_archivo=True)

    @app.post("/planillas-escaneadas/{planilla_id}/aprobar")
    def aprobar_planilla(planilla_id: str, entrada: AprobacionEntrada, sesion: SesionActual):
        filas = [FilaPlanilla(f.legajo, f.nombre_completo, f.presente) for f in entrada.filas]
        try:
            return vista_planilla(planillas.aprobar(planilla_id, filas, sesion.actor))
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/planillas-escaneadas/{planilla_id}/descartar")
    def descartar_planilla(planilla_id: str, entrada: DescarteEntrada, sesion: SesionActual):
        try:
            return vista_planilla(planillas.descartar(planilla_id, entrada.motivo, sesion.actor))
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

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

    @app.get("/informe-anual")
    def informe_anual(sesion: SesionActual, anio: int, empresa: str | None = None, sector: str | None = None):
        if not 2000 <= anio <= 2100:
            raise HTTPException(400, "El año no es válido.")
        return {
            **reportes.informe_anual(anio, padron_para(sesion), empresa or None, sector or None),
            "padron_sin_permiso": padron is not None and not sesion.puede("legajo.leer"),
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


def crear_app(
    configuracion,
    entorno: str = "prueba",
    ruta_base: str = "datos/modulos.sqlite3",
    padron: PadronPersonal | None = None,
    lector: LectorPlanillas | None = None,
) -> FastAPI:
    app = FastAPI(title="Capacitaciones")
    app.include_router(crear_router(configuracion, entorno, ruta_base, padron, lector))
    return app
