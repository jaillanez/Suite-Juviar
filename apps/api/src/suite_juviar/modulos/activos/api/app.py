from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import (
    SesionActual,
    exigir_identidad_configurada,
    exigir_permiso,
)

from ..application.servicios import GestionarActivos
from ..domain.modelos import BODEGAS
from ..domain.puertos import Impresora
from ..infrastructure.sqlite import ActivosSQLite
from ..infrastructure.zebra import (
    PUERTO_ZEBRA,
    ConfiguracionEtiqueta,
    ErrorImpresora,
    ImpresoraZebraRed,
    etiqueta_zpl,
)


class TipoEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=60)
    prefijo: str = Field(min_length=2, max_length=5)


class SectorEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)
    bodega: str


class ActivoEntrada(BaseModel):
    descripcion: str = Field(min_length=1, max_length=120)
    marca: str = Field(default="", max_length=60)
    modelo: str = Field(default="", max_length=60)
    numero_serie: str = Field(default="", max_length=60)


class AltaEntrada(ActivoEntrada):
    tipo_id: str
    sector_id: str


class TrasladoEntrada(BaseModel):
    sector_id: str
    detalle: str = Field(default="", max_length=200)


class SalidaTallerEntrada(BaseModel):
    taller: str = Field(min_length=1, max_length=120)
    motivo: str = Field(min_length=1, max_length=300)


class RegresoTallerEntrada(BaseModel):
    costo: float = Field(ge=0)
    trabajo_realizado: str = Field(default="", max_length=500)
    sector_id: str
    empresa: str


class BajaEntrada(BaseModel):
    motivo: str = Field(min_length=1, max_length=300)


class ImpresoraEntrada(BaseModel):
    direccion: str
    puerto: int = PUERTO_ZEBRA
    dpi: int = 203
    ancho_mm: float = 100
    alto_mm: float = 50


class ImprimirEntrada(BaseModel):
    copias: int = Field(default=1, ge=1, le=50)


def _error(exc: Exception) -> HTTPException:
    return HTTPException(404 if isinstance(exc, LookupError) else 400, str(exc))


def crear_router(
    entorno: str = "prueba",
    ruta_base: str = "datos/modulos.sqlite3",
    crear_impresora: Callable[[str, int], Impresora] = ImpresoraZebraRed,
) -> APIRouter:
    exigir_identidad_configurada(entorno)
    repo = ActivosSQLite(ruta_base)
    servicio = GestionarActivos(repo)
    app = APIRouter()
    operar = [Depends(exigir_permiso("activos.gestionar"))]
    administrar = [Depends(exigir_permiso("parametros.gestionar"))]

    def configuracion() -> ConfiguracionEtiqueta | None:
        guardada = repo.impresora.get("etiquetas")
        return ConfiguracionEtiqueta(**guardada) if guardada else None

    @app.get("/tipos", dependencies=operar)
    def tipos():
        return sorted((asdict(t) for t in repo.tipos.values()), key=lambda t: t["nombre"].casefold())

    @app.post("/tipos", status_code=201, dependencies=operar)
    def crear_tipo(entrada: TipoEntrada):
        try:
            return servicio.guardar_tipo(entrada.nombre, entrada.prefijo)
        except (ValueError, LookupError) as exc:
            raise _error(exc) from exc

    @app.put("/tipos/{tipo_id}", dependencies=operar)
    def editar_tipo(tipo_id: str, entrada: TipoEntrada):
        try:
            return servicio.guardar_tipo(entrada.nombre, entrada.prefijo, tipo_id)
        except (ValueError, LookupError) as exc:
            raise _error(exc) from exc

    @app.delete("/tipos/{tipo_id}", status_code=204, dependencies=operar)
    def eliminar_tipo(tipo_id: str):
        try:
            servicio.eliminar_tipo(tipo_id)
        except (ValueError, LookupError) as exc:
            raise _error(exc) from exc

    @app.get("/sectores", dependencies=operar)
    def sectores():
        return sorted(({**asdict(s), "bodega_nombre": BODEGAS[s.bodega]} for s in repo.sectores.values()),
                      key=lambda s: (s["bodega_nombre"], s["nombre"].casefold()))

    @app.get("/bodegas", dependencies=operar)
    def bodegas():
        return [{"id": clave, "nombre": nombre} for clave, nombre in BODEGAS.items()]

    @app.post("/sectores", status_code=201, dependencies=operar)
    def crear_sector(entrada: SectorEntrada):
        try:
            return servicio.guardar_sector(entrada.nombre, entrada.bodega)
        except (ValueError, LookupError) as exc:
            raise _error(exc) from exc

    @app.put("/sectores/{sector_id}", dependencies=operar)
    def editar_sector(sector_id: str, entrada: SectorEntrada):
        try:
            return servicio.guardar_sector(entrada.nombre, entrada.bodega, sector_id)
        except (ValueError, LookupError) as exc:
            raise _error(exc) from exc

    @app.delete("/sectores/{sector_id}", status_code=204, dependencies=operar)
    def eliminar_sector(sector_id: str):
        try:
            servicio.eliminar_sector(sector_id)
        except (ValueError, LookupError) as exc:
            raise _error(exc) from exc

    @app.get("/impresora", dependencies=operar)
    def ver_impresora():
        config = configuracion()
        return asdict(config) if config else None

    @app.put("/impresora", dependencies=administrar)
    def guardar_impresora(entrada: ImpresoraEntrada):
        try:
            config = ConfiguracionEtiqueta(**entrada.model_dump())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        repo.impresora["etiquetas"] = asdict(config)
        return asdict(config)

    @app.get("/equipos", dependencies=operar)
    def listar(tipo_id: str | None = None, sector_id: str | None = None, texto: str | None = None,
               mas_reparados: bool = False, bodega: str | None = None):
        return servicio.listar(tipo_id, sector_id, texto, mas_reparados, bodega)

    @app.post("/equipos", status_code=201, dependencies=operar)
    def alta(entrada: AltaEntrada, sesion: SesionActual):
        try:
            activo = servicio.dar_de_alta(entrada.tipo_id, entrada.descripcion, entrada.sector_id, sesion.actor,
                                          entrada.marca, entrada.modelo, entrada.numero_serie)
            return servicio.vista(activo)
        except (ValueError, LookupError) as exc:
            raise _error(exc) from exc

    @app.get("/equipos/{codigo}", dependencies=operar)
    def ficha(codigo: str):
        try:
            return servicio.ficha(codigo)
        except LookupError as exc:
            raise _error(exc) from exc

    @app.put("/equipos/{codigo}", dependencies=operar)
    def editar(codigo: str, entrada: ActivoEntrada):
        try:
            return servicio.vista(servicio.editar(codigo, entrada.descripcion, entrada.marca, entrada.modelo,
                                                  entrada.numero_serie))
        except (ValueError, LookupError) as exc:
            raise _error(exc) from exc

    @app.post("/equipos/{codigo}/traslado", dependencies=operar)
    def trasladar(codigo: str, entrada: TrasladoEntrada, sesion: SesionActual):
        try:
            return servicio.vista(servicio.trasladar(codigo, entrada.sector_id, sesion.actor, entrada.detalle))
        except (ValueError, LookupError) as exc:
            raise _error(exc) from exc

    @app.post("/equipos/{codigo}/taller", dependencies=operar)
    def enviar_a_taller(codigo: str, entrada: SalidaTallerEntrada, sesion: SesionActual):
        try:
            return asdict(servicio.enviar_a_taller(codigo, entrada.taller, entrada.motivo, sesion.actor))
        except (ValueError, LookupError) as exc:
            raise _error(exc) from exc

    @app.post("/equipos/{codigo}/regreso", dependencies=operar)
    def registrar_regreso(codigo: str, entrada: RegresoTallerEntrada, sesion: SesionActual):
        try:
            return asdict(servicio.registrar_regreso(codigo, entrada.costo, entrada.trabajo_realizado,
                                                     entrada.sector_id, sesion.actor, entrada.empresa))
        except (ValueError, LookupError) as exc:
            raise _error(exc) from exc

    @app.post("/equipos/{codigo}/baja", dependencies=operar)
    def dar_de_baja(codigo: str, entrada: BajaEntrada, sesion: SesionActual):
        try:
            return servicio.vista(servicio.dar_de_baja(codigo, entrada.motivo, sesion.actor))
        except (ValueError, LookupError) as exc:
            raise _error(exc) from exc

    @app.post("/equipos/{codigo}/etiqueta", dependencies=operar)
    def imprimir(codigo: str, entrada: ImprimirEntrada):
        config = configuracion()
        if config is None:
            raise HTTPException(409, "Falta cargar la impresora de etiquetas en Parámetros.")
        try:
            fila = servicio.vista(servicio.obtener(codigo))
        except LookupError as exc:
            raise _error(exc) from exc
        if fila["estado"] == "DE_BAJA":
            raise HTTPException(400, "El equipo está dado de baja.")
        subtitulo = " · ".join(v for v in (fila["tipo"], fila["marca"], fila["modelo"]) if v)
        zpl = etiqueta_zpl(fila["codigo"], fila["descripcion"], subtitulo, config, entrada.copias)
        try:
            crear_impresora(config.direccion, config.puerto).enviar(zpl)
        except ErrorImpresora as exc:
            raise HTTPException(502, str(exc)) from exc
        return {"ok": True, "copias": entrada.copias}

    return app


def crear_app(entorno: str = "prueba", ruta_base: str = "datos/modulos.sqlite3") -> FastAPI:
    app = FastAPI(title="Activos")
    app.include_router(crear_router(entorno, ruta_base))
    return app
