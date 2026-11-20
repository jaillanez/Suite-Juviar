"""Bandeja de RRHH (certificados médicos y pedidos de EPP por WhatsApp) y recorridos del micro.

Los certificados que no pudieron entrar solos a Salud los completa el servicio médico en
`/salud/pendientes`, con los permisos de Salud: RRHH no ve ahí ni el diagnóstico ni el motivo.
"""

from __future__ import annotations

import logging
import threading
from datetime import date

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Response
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import (
    SesionActual,
    exigir_identidad_configurada,
    exigir_permiso,
)

from ..application.servicios import BandejaRRHH

_registro = logging.getLogger(__name__)


class LegajoEntrada(BaseModel):
    nombre: str = Field(default="", max_length=120)
    dias: int | None = Field(default=None, ge=1, le=365)
    desde: date | None = None
    hasta: date | None = None
    profesional: str = Field(default="", max_length=120)
    resumen: str = Field(default="", max_length=500)
    nota: str = Field(default="", max_length=300)


class NotaEntrada(BaseModel):
    nota: str = Field(default="", max_length=300)


class MotivoEntrada(BaseModel):
    motivo: str = Field(min_length=1, max_length=300)


class SaludEntrada(BaseModel):
    diagnostico_codigo: str = Field(min_length=1, max_length=50)
    dias: int | None = Field(default=None, ge=1, le=365)
    desde: date | None = None
    hasta: date | None = None
    profesional: str = Field(default="", max_length=120)
    resumen: str = Field(default="", max_length=500)
    tipo_accidente: str = Field(default="", max_length=30)


class AsignacionEntrada(BaseModel):
    recorrido_id: int | None = Field(default=None, ge=1)


class RecorridoEntrada(BaseModel):
    sede: str = Field(max_length=30)
    nombre: str = Field(min_length=2, max_length=80)
    activo: bool = True


def crear_router(servicio: BandejaRRHH, entorno: str = "prueba", sincronizar_cada: int | None = None) -> APIRouter:
    exigir_identidad_configurada(entorno)
    if sincronizar_cada:
        _iniciar_sincronizacion(servicio, sincronizar_cada)
    app = APIRouter()
    bandeja = [Depends(exigir_permiso("rrhh.bandeja.gestionar"))]
    micro = [Depends(exigir_permiso("rrhh.micro.gestionar"))]
    # Secreto médico: sólo el perfil médico (lee diagnósticos y carga certificados).
    salud = [Depends(exigir_permiso("salud.diagnostico.leer")), Depends(exigir_permiso("salud.certificado.gestionar"))]

    def hacer(funcion):
        try:
            return funcion()
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    def sincronizar() -> None:
        try:
            servicio.sincronizar()
        except Exception:  # noqa: BLE001 - sin la base de la fila se muestra lo que hay
            _registro.warning("No se pudo leer la base de la fila para la bandeja de RRHH.", exc_info=True)

    @app.get("/mensajes", dependencies=bandeja)
    def listar(estado: str | None = None):
        sincronizar()
        return servicio.listar(estado)

    @app.get("/mensajes/{mensaje_id}/archivo", dependencies=bandeja)
    def archivo(mensaje_id: str):
        mensaje = hacer(lambda: servicio.obtener(mensaje_id))
        if mensaje.archivo is None:
            raise HTTPException(404, "Ese mensaje no tiene archivo.")
        return Response(mensaje.archivo, media_type=mensaje.archivo_tipo,
                        headers={"Content-Disposition": "inline", "X-Content-Type-Options": "nosniff",
                                 "Cache-Control": "no-store"})

    @app.post("/mensajes/{mensaje_id}/legajo", dependencies=bandeja)
    def pasar_al_legajo(mensaje_id: str, entrada: LegajoEntrada, sesion: SesionActual):
        datos = entrada.model_dump()
        return hacer(lambda: servicio.vista(servicio.pasar_al_legajo(mensaje_id, datos, sesion.actor)))

    @app.post("/mensajes/{mensaje_id}/atender", dependencies=bandeja)
    def atender(mensaje_id: str, entrada: NotaEntrada, sesion: SesionActual):
        return hacer(lambda: servicio.vista(servicio.atender(mensaje_id, entrada.nota, sesion.actor)))

    @app.post("/mensajes/{mensaje_id}/descartar", dependencies=bandeja)
    def descartar(mensaje_id: str, entrada: MotivoEntrada, sesion: SesionActual):
        return hacer(lambda: servicio.vista(servicio.descartar(mensaje_id, entrada.motivo, sesion.actor)))

    @app.get("/salud/pendientes", dependencies=salud)
    def pendientes_salud(sesion: SesionActual):
        return servicio.pendientes_salud(sesion.actor)

    @app.get("/salud/pendientes/{mensaje_id}/archivo", dependencies=salud)
    def archivo_salud(mensaje_id: str, sesion: SesionActual):
        mensaje = hacer(lambda: servicio.archivo_salud(mensaje_id, sesion.actor))
        return Response(mensaje.archivo, media_type=mensaje.archivo_tipo,
                        headers={"Content-Disposition": "inline", "X-Content-Type-Options": "nosniff",
                                 "Cache-Control": "no-store"})

    @app.post("/salud/pendientes/{mensaje_id}/cargar", dependencies=salud)
    def completar_salud(mensaje_id: str, entrada: SaludEntrada, sesion: SesionActual):
        try:
            return hacer(lambda: servicio.vista_salud(
                servicio.completar_salud(mensaje_id, entrada.model_dump(), sesion.actor)))
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.get("/personal", dependencies=micro)
    def personal():
        try:
            return servicio.personal()
        except Exception as exc:
            _registro.warning("No se pudo leer el personal del bot.", exc_info=True)
            raise HTTPException(503, "No se pudo leer la base de la fila.") from exc

    @app.put("/personal/{telefono}/recorrido", dependencies=micro)
    def asignar_recorrido(entrada: AsignacionEntrada, sesion: SesionActual,
                          telefono: str = Path(pattern=r"^\d{8,20}$")):
        """Sólo el recorrido: el alta, la baja y los datos del personal siguen en «Personal en el bot»."""
        try:
            return servicio.asignar_recorrido(telefono, entrada.recorrido_id, sesion.actor)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.get("/sedes", dependencies=micro)
    def sedes():
        return [{"id": clave, "nombre": nombre} for clave, nombre in servicio.sedes.items()]

    @app.get("/recorridos", dependencies=micro)
    def recorridos():
        try:
            return servicio.recorridos()
        except Exception as exc:
            _registro.warning("No se pudieron leer los recorridos del micro.", exc_info=True)
            raise HTTPException(503, "No se pudo leer la base de la fila.") from exc

    @app.post("/recorridos", status_code=201, dependencies=micro)
    def crear_recorrido(entrada: RecorridoEntrada, sesion: SesionActual):
        return _guardar(None, entrada, sesion)

    @app.put("/recorridos/{recorrido_id}", dependencies=micro)
    def editar_recorrido(recorrido_id: int, entrada: RecorridoEntrada, sesion: SesionActual):
        return _guardar(recorrido_id, entrada, sesion)

    def _guardar(recorrido_id: int | None, entrada: RecorridoEntrada, sesion: SesionActual):
        try:
            return servicio.guardar_recorrido(recorrido_id, entrada.sede, entrada.nombre, entrada.activo,
                                              sesion.actor)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

    return app


def _iniciar_sincronizacion(servicio: BandejaRRHH, cada_segundos: int) -> threading.Thread:
    def ciclo() -> None:
        while True:
            threading.Event().wait(cada_segundos)
            try:
                servicio.sincronizar()
            except Exception:  # noqa: BLE001 - el ciclo no se corta por un error puntual
                _registro.exception("No se pudo sincronizar la bandeja de RRHH con la base de la fila.")

    hilo = threading.Thread(target=ciclo, name="rrhh-whatsapp", daemon=True)
    hilo.start()
    return hilo


def crear_app(servicio: BandejaRRHH, entorno: str = "prueba") -> FastAPI:
    app = FastAPI(title="RRHH por WhatsApp")
    app.include_router(crear_router(servicio, entorno))
    return app
