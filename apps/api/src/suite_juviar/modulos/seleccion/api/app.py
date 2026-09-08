from __future__ import annotations

from base64 import b64decode, b64encode
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import (
    SesionActual,
    exigir_identidad_configurada,
    exigir_permiso,
)

from ..application.extraccion import ExtraerDatosCV
from ..application.ranking import EvaluarBusqueda, ordenar_resultados
from ..domain.modelos import (
    Busqueda,
    ConfirmacionCampo,
    ConsultaOriginal,
    CVOriginal,
    OrigenCV,
    PerfilBusqueda,
)
from ..infrastructure.extraccion_pdf import CamposPorReglasProvisorias, TextoPDF
from ..infrastructure.extracciones_memoria import ExtraccionesEnMemoria
from ..infrastructure.memoria import OriginalesEnMemoria


class BusquedaEntrada(BaseModel):
    nombre: str = Field(min_length=1)
    perfil: PerfilBusqueda
    definido_por: str | None = None
    edad_minima: int | None = Field(default=None, ge=0)
    edad_maxima: int | None = Field(default=None, ge=0)
    secundaria_completa: bool = False


class LoteEntrada(BaseModel):
    archivos: list[dict[str, str]] = Field(min_length=1)


class ConfirmacionEntrada(BaseModel):
    valor: str = Field(min_length=1)


def crear_app(perfiles, entorno: str = "prueba") -> FastAPI:
    exigir_identidad_configurada(entorno)
    app = FastAPI(
        title="Selección de personal",
        dependencies=[Depends(exigir_permiso("seleccion.gestionar"))],
    )
    originales = OriginalesEnMemoria()
    extracciones = ExtraccionesEnMemoria()
    extraer = ExtraerDatosCV(originales, extracciones, TextoPDF(), CamposPorReglasProvisorias())
    evaluar = EvaluarBusqueda(perfiles)
    busquedas: dict[str, Busqueda] = {}

    @app.get("/estado")
    def estado():
        return {"fuente_simulada": True, "reglas_extraccion": "NO_VALIDADAS", "dueno_dato": "RRHH"}

    @app.get("/busquedas")
    def listar_busquedas():
        return list(busquedas.values())

    @app.get("/busquedas/{busqueda_id}")
    def ver_busqueda(busqueda_id: str):
        busqueda = busquedas.get(busqueda_id)
        if busqueda is None:
            raise HTTPException(404, "Búsqueda inexistente")
        return busqueda

    @app.post("/busquedas", status_code=201)
    def crear_busqueda(entrada: BusquedaEntrada, sesion: SesionActual):
        busqueda = Busqueda(
            id=str(uuid4()), nombre=entrada.nombre, perfil=entrada.perfil,
            definido_por=sesion.actor, definido_en=datetime.now(UTC),
            edad_minima=entrada.edad_minima, edad_maxima=entrada.edad_maxima,
            secundaria_completa=entrada.secundaria_completa,
        )
        busquedas[busqueda.id] = busqueda
        return busqueda

    @app.post("/cvs/lote", status_code=201)
    def cargar_lote(entrada: LoteEntrada):
        ids = []
        for archivo in entrada.archivos:
            try:
                contenido = b64decode(archivo["contenido_base64"], validate=True)
                nombre = archivo["nombre"]
            except (KeyError, ValueError) as exc:
                raise HTTPException(400, "Cada archivo requiere nombre y contenido base64 válido") from exc
            digest = __import__("hashlib").sha256(contenido).hexdigest()
            original = CVOriginal(digest, OrigenCV.CORREO, f"carga-manual:{digest}", nombre,
                                  contenido, digest, datetime.now(UTC), datetime.now(UTC),
                                  fuente_simulada=True)
            if originales.guardar_original(original):
                extraer.ejecutar(digest)
            ids.append(digest)
        return {"incorporados": ids, "marca": "DATOS SIMULADOS — SIN VALIDEZ"}

    @app.get("/cvs")
    def listar_cvs(busqueda_id: str | None = None):
        busqueda = busquedas.get(busqueda_id) if busqueda_id else None
        filas = []
        for original in originales.listar_originales():
            extraccion = extracciones.obtener_extraccion(original.id)
            resultado = evaluar.ejecutar(busqueda, extraccion) if busqueda and extraccion else None
            filas.append({
                "id": original.id, "nombre": original.nombre_archivo,
                "requiere_revision": bool(extraccion and extraccion.requiere_revision),
                "campos": list(extraccion.campos) if extraccion else [],
                "campos_pendientes": list(extraccion.campos_pendientes) if extraccion else [],
                "resultado": resultado,
            })
        if busqueda:
            por_id = {fila["id"]: fila for fila in filas}
            ordenados = ordenar_resultados([fila["resultado"] for fila in filas if fila["resultado"]])
            return [por_id[resultado.id_original] for resultado in ordenados]
        return filas

    @app.get("/revision")
    def revision():
        return [fila for fila in listar_cvs() if fila["requiere_revision"]]

    @app.get("/cvs/{cv_id}")
    def ficha_cv(cv_id: str, busqueda_id: str | None = None):
        original = originales.obtener_original(cv_id)
        extraccion = extracciones.obtener_extraccion(cv_id)
        if original is None or extraccion is None:
            raise HTTPException(404, "CV inexistente")
        busqueda = busquedas.get(busqueda_id) if busqueda_id else None
        return {
            "id": cv_id,
            "nombre": original.nombre_archivo,
            "campos": list(extraccion.campos),
            "pendientes": list(extraccion.campos_pendientes),
            "confirmaciones": extracciones.confirmaciones(cv_id),
            "resultado": evaluar.ejecutar(busqueda, extraccion) if busqueda else None,
            "marca": "DATOS SIMULADOS — SIN VALIDEZ",
        }

    @app.put("/cvs/{cv_id}/campos/{campo}/confirmacion")
    def confirmar_campo(
        cv_id: str,
        campo: str,
        entrada: ConfirmacionEntrada,
        sesion: SesionActual,
    ):
        extraccion = extracciones.obtener_extraccion(cv_id)
        if extraccion is None:
            raise HTTPException(404, "CV inexistente")
        extraido = next((valor for valor in extraccion.campos if valor.nombre == campo), None)
        if extraido is None:
            raise HTTPException(400, "No existe ese campo extraído")
        confirmacion = ConfirmacionCampo(
            cv_id, campo, entrada.valor, sesion.actor, datetime.now(UTC)
        )
        extracciones.confirmar(confirmacion)
        return confirmacion

    @app.get("/cvs/{cv_id}/original")
    def original(cv_id: str, sesion: SesionActual):
        cv = originales.obtener_original(cv_id)
        if cv is None:
            raise HTTPException(404, "CV inexistente")
        extracciones.auditar_original(ConsultaOriginal(cv_id, sesion.actor, datetime.now(UTC)))
        return {"nombre": cv.nombre_archivo, "contenido_base64": b64encode(cv.contenido).decode(),
                "marca": "DATOS SIMULADOS — SIN VALIDEZ"}

    @app.get("/cvs/{cv_id}/auditoria")
    def auditoria(cv_id: str):
        return extracciones.consultas_original(cv_id)

    return app
