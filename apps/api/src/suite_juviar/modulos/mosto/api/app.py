from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import (
    SesionActual,
    exigir_identidad_configurada,
    exigir_permiso,
)

from ..application.servicios import GestionarMosto
from ..domain.modelos import BODEGAS, TIPOS, Etapa

Positivo = Annotated[float, Field(gt=0, lt=1e9, allow_inf_nan=False)]
Medida = Annotated[float, Field(ge=0, lt=1000, allow_inf_nan=False)]


class AnalisisEntrada(BaseModel):
    azucar_gl: Medida
    absorbancia_520: Medida | None = None
    alcohol: Medida | None = None
    observaciones: str = Field(default="", max_length=300)


class CompraEntrada(BaseModel):
    proveedor: str = Field(min_length=1, max_length=120)
    cuit: str
    tipo: Literal["sulfitado", "virgen"]
    litros: Positivo
    precio_base: Positivo


class DecisionEntrada(BaseModel):
    aprueba: bool
    motivo: str = Field(default="", max_length=300)


class PiletaEntrada(AnalisisEntrada):
    pileta: str = Field(min_length=1, max_length=40)
    litros: Positivo


class MargenEntrada(BaseModel):
    sin_margen: bool
    motivo: str = Field(default="", max_length=300)


class ViajeEntrada(BaseModel):
    compra_id: str
    bodega: str
    patente: str = Field(min_length=1, max_length=12)
    litros: Positivo


class LugarEntrada(BaseModel):
    lugar: str = Field(min_length=1, max_length=80)
    nota: str = Field(default="", max_length=200)


class DestinatarioEntrada(BaseModel):
    nombre: str = Field(max_length=80)
    correo: str = Field(default="", max_length=120)
    telefono: str = Field(default="", max_length=20)


class ParametrosEntrada(BaseModel):
    azucar_referencia: Medida
    margen_gl: Medida
    horas_virgen: Medida | None = None
    destinatarios: list[DestinatarioEntrada] = Field(default_factory=list, max_length=30)


def _error(exc: Exception) -> HTTPException:
    return HTTPException(404 if isinstance(exc, LookupError) else 400, str(exc))


def crear_router(servicio: GestionarMosto, entorno: str = "prueba") -> APIRouter:
    exigir_identidad_configurada(entorno)
    app = APIRouter()
    leer = [Depends(exigir_permiso("mosto.leer"))]
    comprar = [Depends(exigir_permiso("mosto.compras.gestionar"))]
    laboratorio = [Depends(exigir_permiso("mosto.laboratorio"))]
    produccion = [Depends(exigir_permiso("mosto.produccion"))]
    comercial = [Depends(exigir_permiso("mosto.comercial"))]
    bascula = [Depends(exigir_permiso("mosto.viajes.ingresar"))]
    administrar = [Depends(exigir_permiso("parametros.gestionar"))]

    def hacer(funcion):
        try:
            return funcion()
        except (ValueError, LookupError) as exc:
            raise _error(exc) from exc

    @app.get("/catalogo", dependencies=leer)
    def catalogo():
        p = servicio.parametros()
        return {"tipos": TIPOS, "bodegas": BODEGAS, "azucar_referencia": p.azucar_referencia,
                "margen_gl": p.margen_gl, "horas_virgen": p.horas_virgen}

    @app.get("/parametros", dependencies=administrar)
    def ver_parametros():
        return asdict(servicio.parametros())

    @app.put("/parametros", dependencies=administrar)
    def guardar_parametros(entrada: ParametrosEntrada, sesion: SesionActual):
        return hacer(lambda: asdict(servicio.guardar_parametros(
            entrada.azucar_referencia, entrada.margen_gl, entrada.horas_virgen,
            [d.model_dump() for d in entrada.destinatarios], sesion.actor)))

    @app.get("/compras", dependencies=leer)
    def compras():
        return servicio.listar()

    @app.post("/compras", status_code=201, dependencies=comprar)
    def crear_compra(entrada: CompraEntrada, sesion: SesionActual):
        return hacer(lambda: servicio.vista(servicio.crear_compra(
            entrada.proveedor, entrada.cuit, entrada.tipo, entrada.litros, entrada.precio_base, sesion.actor)))

    @app.get("/compras/{compra_id}", dependencies=leer)
    def ficha(compra_id: str):
        return hacer(lambda: servicio.ficha(compra_id))

    @app.post("/compras/{compra_id}/analisis", dependencies=laboratorio)
    def analisis_oferta(compra_id: str, entrada: AnalisisEntrada, sesion: SesionActual):
        return hacer(lambda: servicio.ficha(servicio.cargar_analisis_oferta(
            compra_id, entrada.model_dump(), sesion.actor).id))

    def decidir(compra_id: str, etapa: Etapa, entrada: DecisionEntrada, actor: str):
        return hacer(lambda: servicio.ficha(servicio.decidir(
            compra_id, etapa, entrada.aprueba, entrada.motivo, actor).id))

    @app.post("/compras/{compra_id}/calidad", dependencies=laboratorio)
    def calidad(compra_id: str, entrada: DecisionEntrada, sesion: SesionActual):
        return decidir(compra_id, Etapa.CALIDAD, entrada, sesion.actor)

    @app.post("/compras/{compra_id}/produccion", dependencies=produccion)
    def decision_produccion(compra_id: str, entrada: DecisionEntrada, sesion: SesionActual):
        return decidir(compra_id, Etapa.PRODUCCION, entrada, sesion.actor)

    @app.post("/compras/{compra_id}/comercial", dependencies=comercial)
    def decision_comercial(compra_id: str, entrada: DecisionEntrada, sesion: SesionActual):
        return decidir(compra_id, Etapa.COMERCIAL, entrada, sesion.actor)

    @app.post("/compras/{compra_id}/piletas", dependencies=laboratorio)
    def pileta(compra_id: str, entrada: PiletaEntrada, sesion: SesionActual):
        datos = entrada.model_dump(exclude={"pileta", "litros"})
        return hacer(lambda: servicio.ficha(servicio.agregar_pileta(
            compra_id, entrada.pileta, entrada.litros, datos, sesion.actor).id))

    @app.post("/compras/{compra_id}/margen", dependencies=comercial)
    def margen(compra_id: str, entrada: MargenEntrada, sesion: SesionActual):
        return hacer(lambda: servicio.ficha(servicio.excepcion_margen(
            compra_id, entrada.sin_margen, entrada.motivo, sesion.actor).id))

    @app.post("/compras/{compra_id}/cerrar", dependencies=comercial)
    def cerrar(compra_id: str, sesion: SesionActual):
        return hacer(lambda: servicio.ficha(servicio.cerrar(compra_id, sesion.actor).id))

    @app.get("/viajes", dependencies=leer)
    def viajes(en_planta: bool = False):
        return servicio.listar_viajes(en_planta)

    @app.post("/viajes", status_code=201, dependencies=bascula)
    def ingresar(entrada: ViajeEntrada, sesion: SesionActual):
        return hacer(lambda: servicio.vista_viaje(servicio.ingresar(
            entrada.compra_id, entrada.bodega, entrada.patente, entrada.litros, sesion.actor)))

    @app.post("/viajes/{viaje_id}/analisis", dependencies=laboratorio)
    def analisis_viaje(viaje_id: str, entrada: AnalisisEntrada, sesion: SesionActual):
        return hacer(lambda: servicio.vista_viaje(servicio.analizar_viaje(
            viaje_id, entrada.model_dump(), sesion.actor)))

    @app.post("/viajes/{viaje_id}/descarga", dependencies=produccion)
    def descarga(viaje_id: str, entrada: LugarEntrada, sesion: SesionActual):
        return hacer(lambda: servicio.vista_viaje(servicio.descargar(
            viaje_id, entrada.lugar, entrada.nota, sesion.actor)))

    @app.post("/viajes/{viaje_id}/recorrido", dependencies=produccion)
    def recorrido(viaje_id: str, entrada: LugarEntrada, sesion: SesionActual):
        return hacer(lambda: servicio.vista_viaje(servicio.mover(
            viaje_id, entrada.lugar, entrada.nota, sesion.actor)))

    @app.get("/avisos", dependencies=leer)
    def avisos():
        return servicio.avisos()

    return app
