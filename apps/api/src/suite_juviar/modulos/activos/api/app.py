from __future__ import annotations

import base64
import binascii
import logging
import threading
from collections.abc import Callable
from dataclasses import asdict
from io import BytesIO
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Response
from PIL import Image as PILImage
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import (
    SesionActual,
    exigir_identidad_configurada,
    exigir_permiso,
)

from ..application.remitos import GestionarRemitos
from ..application.servicios import GestionarActivos
from ..domain.modelos import BODEGAS
from ..domain.puertos import Impresora, PuertaGuardia
from ..infrastructure.guardia_dmz import PuertaSinConfigurar
from ..infrastructure.remito_pdf import remito_pdf
from ..infrastructure.sqlite import ActivosSQLite, RemitosSQLite
from ..infrastructure.zebra import (
    PUERTO_ZEBRA,
    ConfiguracionEtiqueta,
    ErrorImpresora,
    ImpresoraZebraRed,
    etiqueta_zpl,
)

Costo = Annotated[float, Field(ge=0, lt=1e10, allow_inf_nan=False)]
_registro = logging.getLogger(__name__)


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
    costo: Costo
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


class ItemEntrada(BaseModel):
    codigo: str | None = Field(default=None, max_length=20)
    descripcion: str = Field(default="", max_length=200)
    cantidad: int = Field(default=1, ge=1, le=999)


class RemitoEntrada(BaseModel):
    bodega: str = Field(max_length=20)
    destino: str = Field(min_length=1, max_length=120)
    motivo: str = Field(min_length=1, max_length=300)
    items: list[ItemEntrada] = Field(min_length=1, max_length=50)


class FirmaEntrada(BaseModel):
    modo: Literal["celular", "papel"]
    imagen: str | None = Field(default=None, max_length=420_000)  # PNG en base64


class AnularEntrada(BaseModel):
    motivo: str = Field(min_length=1, max_length=300)


class ParametrosRemitosEntrada(BaseModel):
    dias_maximos_fuera: int | None = Field(default=None, ge=1, le=365)
    modo_whatsapp: Literal["revision", "directo"]


def _error(exc: Exception) -> HTTPException:
    return HTTPException(404 if isinstance(exc, LookupError) else 400, str(exc))


def crear_router(
    entorno: str = "prueba",
    ruta_base: str = "datos/modulos.sqlite3",
    crear_impresora: Callable[[str, int], Impresora] = ImpresoraZebraRed,
    puerta: PuertaGuardia | None = None,
    sincronizar_cada: int | None = None,
) -> APIRouter:
    exigir_identidad_configurada(entorno)
    repo = ActivosSQLite(ruta_base)
    servicio = GestionarActivos(repo)
    remitos = GestionarRemitos(RemitosSQLite(ruta_base), servicio, puerta or PuertaSinConfigurar())
    if sincronizar_cada:
        _iniciar_sincronizacion(remitos, sincronizar_cada)
    app = APIRouter()
    operar = [Depends(exigir_permiso("activos.gestionar"))]
    firmar = [Depends(exigir_permiso("activos.remitos.firmar"))]
    administrar = [Depends(exigir_permiso("parametros.gestionar"))]

    def hacer(funcion):
        try:
            return funcion()
        except (ValueError, LookupError) as exc:
            raise _error(exc) from exc

    def sincronizar() -> None:
        try:
            remitos.sincronizar()
        except Exception:  # noqa: BLE001 - sin la base de la fila se muestra lo que hay
            _registro.warning("No se pudo leer la guardia para los remitos.", exc_info=True)

    @app.get("/remitos", dependencies=operar)
    def listar_remitos(estado: str | None = None):
        sincronizar()
        return remitos.listar(estado)

    @app.post("/remitos", status_code=201, dependencies=operar)
    def crear_remito(entrada: RemitoEntrada, sesion: SesionActual):
        return hacer(lambda: remitos.vista(remitos.crear(
            entrada.bodega, entrada.destino, entrada.motivo, [i.model_dump() for i in entrada.items], sesion.actor)))

    @app.get("/remitos/{remito_id}", dependencies=operar)
    def ver_remito(remito_id: str):
        return hacer(lambda: remitos.vista(remitos.obtener(remito_id)))

    @app.put("/remitos/{remito_id}", dependencies=operar)
    def editar_remito(remito_id: str, entrada: RemitoEntrada):
        return hacer(lambda: remitos.vista(remitos.editar(
            remito_id, entrada.bodega, entrada.destino, entrada.motivo, [i.model_dump() for i in entrada.items])))

    @app.post("/remitos/{remito_id}/firma", dependencies=firmar)
    def firmar_remito(remito_id: str, entrada: FirmaEntrada, sesion: SesionActual):
        imagen = None
        if entrada.modo == "celular":
            try:
                imagen = base64.b64decode((entrada.imagen or "").split(",")[-1], validate=True)
                if imagen:
                    with PILImage.open(BytesIO(imagen)) as dibujo:
                        if dibujo.format != "PNG" or dibujo.width > 2000 or dibujo.height > 1000:
                            raise ValueError
                        dibujo.load()
            except (binascii.Error, ValueError, OSError):
                raise HTTPException(400, "La firma no llegó bien; volvé a firmar.") from None
        return hacer(lambda: remitos.vista(remitos.firmar(remito_id, entrada.modo, imagen, sesion.actor)))

    @app.post("/remitos/{remito_id}/anular", dependencies=firmar)
    def anular_remito(remito_id: str, entrada: AnularEntrada, sesion: SesionActual):
        return hacer(lambda: remitos.vista(remitos.anular(remito_id, entrada.motivo, sesion.actor)))

    @app.post("/remitos/{remito_id}/items/{indice}/regreso", dependencies=operar)
    def regreso_item(remito_id: str, indice: int, sesion: SesionActual):
        return hacer(lambda: remitos.vista(remitos.marcar_regreso(remito_id, indice, sesion.actor)))

    @app.post("/remitos/{remito_id}/equipos/{codigo}/regreso", dependencies=operar)
    def regreso_equipo(remito_id: str, codigo: str, entrada: RegresoTallerEntrada, sesion: SesionActual):
        return hacer(lambda: remitos.vista(remitos.regreso_equipo(
            remito_id, codigo, entrada.costo, entrada.trabajo_realizado, entrada.sector_id, entrada.empresa,
            sesion.actor)))

    @app.get("/remitos/{remito_id}/pdf", dependencies=operar)
    def pdf_remito(remito_id: str):
        remito = hacer(lambda: remitos.obtener(remito_id))
        return Response(remito_pdf(remito), media_type="application/pdf", headers={
            "Content-Disposition": f'inline; filename="remito-{remito.numero:06d}.pdf"'})

    @app.get("/remitos/{remito_id}/foto", dependencies=operar)
    def foto_remito(remito_id: str):
        remito = hacer(lambda: remitos.obtener(remito_id))
        if remito.foto is None:
            raise HTTPException(404, "Ese remito no tiene foto.")
        return Response(remito.foto, media_type=remito.foto_tipo or "image/jpeg")

    @app.get("/mensajes-whatsapp", dependencies=operar)
    def mensajes_whatsapp():
        sincronizar()
        return remitos.mensajes()

    @app.get("/mensajes-whatsapp/{mensaje_id}/foto", dependencies=operar)
    def foto_mensaje(mensaje_id: str):
        mensaje = hacer(lambda: remitos.obtener_mensaje(mensaje_id))
        if mensaje.foto is None:
            raise HTTPException(404, "Ese mensaje no tiene foto.")
        return Response(mensaje.foto, media_type=mensaje.foto_tipo or "image/jpeg")

    @app.post("/mensajes-whatsapp/{mensaje_id}/remito", status_code=201, dependencies=operar)
    def remito_desde_mensaje(mensaje_id: str, sesion: SesionActual):
        return hacer(lambda: remitos.vista(remitos.armar_desde_mensaje(mensaje_id, sesion.actor)))

    @app.post("/mensajes-whatsapp/{mensaje_id}/descartar", status_code=204, dependencies=operar)
    def descartar_mensaje(mensaje_id: str, sesion: SesionActual):
        hacer(lambda: remitos.descartar_mensaje(mensaje_id, sesion.actor))

    @app.get("/parametros-remitos", dependencies=operar)
    def ver_parametros_remitos():
        p = remitos.parametros()
        return {**asdict(p), "modo_whatsapp": p.modo_whatsapp.value}

    @app.put("/parametros-remitos", dependencies=administrar)
    def guardar_parametros_remitos(entrada: ParametrosRemitosEntrada, sesion: SesionActual):
        p = hacer(lambda: remitos.guardar_parametros(entrada.dias_maximos_fuera, entrada.modo_whatsapp, sesion.actor))
        return {**asdict(p), "modo_whatsapp": p.modo_whatsapp.value}

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


def _iniciar_sincronizacion(remitos: GestionarRemitos, cada_segundos: int) -> threading.Thread:
    def ciclo() -> None:
        while True:
            threading.Event().wait(cada_segundos)
            try:
                remitos.sincronizar()
            except Exception:  # noqa: BLE001 - el ciclo no se corta por un error puntual
                _registro.exception("No se pudo sincronizar los remitos con la guardia.")

    hilo = threading.Thread(target=ciclo, name="remitos-guardia", daemon=True)
    hilo.start()
    return hilo


def crear_app(entorno: str = "prueba", ruta_base: str = "datos/modulos.sqlite3") -> FastAPI:
    app = FastAPI(title="Activos")
    app.include_router(crear_router(entorno, ruta_base))
    return app
