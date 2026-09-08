from __future__ import annotations

from base64 import b64decode, b64encode
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ..application.extraccion import ExtraerDatosCV
from ..application.ranking import EvaluarBusqueda, ordenar_resultados
from ..domain.modelos import Busqueda, CVOriginal, OrigenCV, PerfilBusqueda
from ..infrastructure.extraccion_pdf import CamposPorReglasProvisorias, TextoPDF
from ..infrastructure.extracciones_memoria import ExtraccionesEnMemoria
from ..infrastructure.memoria import OriginalesEnMemoria


class BusquedaEntrada(BaseModel):
    nombre: str = Field(min_length=1)
    perfil: PerfilBusqueda
    definido_por: str = Field(min_length=1)
    edad_minima: int | None = Field(default=None, ge=0)
    edad_maxima: int | None = Field(default=None, ge=0)
    secundaria_completa: bool = False


class LoteEntrada(BaseModel):
    archivos: list[dict[str, str]] = Field(min_length=1)


def crear_app(perfiles) -> FastAPI:
    app = FastAPI(title="Selección de personal")
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

    @app.post("/busquedas", status_code=201)
    def crear_busqueda(entrada: BusquedaEntrada):
        busqueda = Busqueda(
            id=str(uuid4()), nombre=entrada.nombre, perfil=entrada.perfil,
            definido_por=entrada.definido_por, definido_en=datetime.now(UTC),
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

    @app.get("/cvs/{cv_id}/original")
    def original(cv_id: str):
        cv = originales.obtener_original(cv_id)
        if cv is None:
            raise HTTPException(404, "CV inexistente")
        return {"nombre": cv.nombre_archivo, "contenido_base64": b64encode(cv.contenido).decode(),
                "marca": "DATOS SIMULADOS — SIN VALIDEZ"}

    return app
