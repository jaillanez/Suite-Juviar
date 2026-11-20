from __future__ import annotations

import base64
import binascii
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import (
    SesionActual,
    exigir_identidad_configurada,
    exigir_permiso,
)

from ..application.servicios import FaltaClaveServidor, GestionarControles
from ..domain.modelos import ErrorARCA

Importe = Annotated[float, Field(gt=0, lt=1e12, allow_inf_nan=False)]
Cuit = Annotated[str, Field(max_length=13)]


class FacturaEntrada(BaseModel):
    empresa: Literal["ENAV", "JUBIAR"]
    cuit_emisor: Cuit
    razon_social: str = Field(default="", max_length=120)
    tipo_comprobante: int = Field(gt=0, lt=1000)
    punto_venta: int = Field(gt=0, le=99999)
    numero: int = Field(gt=0, le=99999999)
    fecha: date
    importe_total: Importe
    autorizacion: Literal["CAE", "CAEA", "CAI", "CF"]
    codigo_autorizacion: str = Field(default="", max_length=20)


# La foto llega ya comprimida por el navegador (~1,5 MB); el servidor acepta hasta 2 MB.
FotoBase64 = Annotated[str, Field(min_length=1, max_length=2_800_000)]


class FacturaQREntrada(BaseModel):
    qr: str = Field(min_length=1, max_length=2000)
    foto_base64: FotoBase64
    empresa: Literal["ENAV", "JUBIAR"] | None = None


class FotoEntrada(BaseModel):
    foto_base64: FotoBase64


class FacturaConfirmadaEntrada(BaseModel):
    factura: FacturaEntrada
    foto_base64: FotoBase64


def _foto(texto: str) -> bytes:
    try:
        return base64.b64decode(texto, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(400, "La foto no llegó bien: sacala de nuevo.") from exc


class ConstanciaEntrada(BaseModel):
    contenido_base64: str = Field(min_length=1, max_length=14_000_000)
    resultado: Literal["ok", "alerta"]
    nota: str = Field(default="", max_length=300)


class ParametrosEntrada(BaseModel):
    controles_activos: list[Annotated[int, Field(ge=1, le=5)]] = Field(max_length=5)
    excluir_controlador_fiscal: bool
    ambiente: Literal["homologacion", "produccion"]
    cuit_representante: Cuit
    cuit_empresas: dict[Literal["ENAV", "JUBIAR"], Annotated[str, Field(max_length=13)]]
    url_apocrifas: str = Field(max_length=300)
    url_rg18: str = Field(max_length=300)
    enlaces_impositivo: list[Annotated[str, Field(max_length=300)]] = Field(min_length=1, max_length=6)


class CertificadoEntrada(BaseModel):
    certificado_pem: str = Field(min_length=1, max_length=20000)


def crear_router(servicio: GestionarControles, entorno: str = "prueba") -> APIRouter:
    exigir_identidad_configurada(entorno)
    app = APIRouter()
    operar = [Depends(exigir_permiso("controles_fiscales.operar"))]
    administrar = [Depends(exigir_permiso("parametros.gestionar"))]

    def hacer(funcion):
        try:
            return funcion()
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except FaltaClaveServidor as exc:
            raise HTTPException(503, str(exc)) from exc
        except ErrorARCA as exc:
            raise HTTPException(502, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/catalogo", dependencies=operar)
    def catalogo():
        return servicio.catalogo()

    @app.get("/facturas", dependencies=operar)
    def facturas(solo_alertas: bool = False):
        return servicio.listar(solo_alertas)

    @app.post("/facturas", status_code=201, dependencies=operar)
    def crear(entrada: FacturaEntrada, sesion: SesionActual):
        return hacer(lambda: servicio.vista(servicio.crear_factura(entrada.model_dump(), sesion.actor)))

    @app.get("/facturas/{factura_id}", dependencies=operar)
    def ficha(factura_id: str):
        return hacer(lambda: servicio.vista(servicio.obtener(factura_id)))

    @app.post("/facturas/{factura_id}/controles", dependencies=operar)
    def correr(factura_id: str, sesion: SesionActual):
        return hacer(lambda: servicio.vista(servicio.correr(factura_id, sesion.actor)))

    @app.post("/facturas/{factura_id}/controles/{numero}/constancia", dependencies=operar)
    def subir(factura_id: str, numero: Annotated[int, Path(ge=1, le=5)], entrada: ConstanciaEntrada,
              sesion: SesionActual):
        try:
            contenido = base64.b64decode(entrada.contenido_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(400, "El archivo no llegó bien: probá subirlo de nuevo.") from exc
        return hacer(lambda: servicio.vista(servicio.subir_constancia(
            factura_id, numero, contenido, entrada.resultado, entrada.nota, sesion.actor)))

    @app.get("/facturas/{factura_id}/controles/{numero}/pdf", dependencies=operar)
    def pdf(factura_id: str, numero: Annotated[int, Path(ge=1, le=5)]):
        nombre, contenido = hacer(lambda: servicio.archivo(factura_id, numero))
        return Response(contenido, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{nombre}"',
                                 "X-Content-Type-Options": "nosniff"})

    @app.get("/facturas/{factura_id}/foto", dependencies=operar)
    def foto(factura_id: str):
        tipo, contenido = hacer(lambda: servicio.foto(factura_id))
        return Response(contenido, media_type=tipo,
                        headers={"Content-Disposition": "inline", "X-Content-Type-Options": "nosniff",
                                 "Cache-Control": "no-store"})

    # --- Desde el celular: una foto de la factura ---------------------------
    @app.post("/celular/qr", dependencies=operar)
    def desde_qr(entrada: FacturaQREntrada, sesion: SesionActual):
        foto = _foto(entrada.foto_base64)
        return hacer(lambda: servicio.cargar_desde_qr(entrada.qr, foto, entrada.empresa, sesion.actor))

    @app.post("/celular/leer", dependencies=operar)
    def leer(entrada: FotoEntrada, sesion: SesionActual):
        foto = _foto(entrada.foto_base64)
        return hacer(lambda: servicio.leer_foto(foto, sesion.actor))

    @app.post("/celular/confirmar", dependencies=operar)
    def confirmar(entrada: FacturaConfirmadaEntrada, sesion: SesionActual):
        foto = _foto(entrada.foto_base64)
        return hacer(lambda: servicio.cargar_confirmada(entrada.factura.model_dump(), foto, sesion.actor))

    @app.post("/padrones/{nombre}/actualizar", dependencies=operar)
    def actualizar(nombre: Literal["apocrifas", "rg18"]):
        hacer(lambda: servicio.actualizar_padron(nombre))
        return servicio.padrones_info()

    @app.get("/parametros", dependencies=administrar)
    def ver_parametros():
        return servicio.vista_parametros()

    @app.put("/parametros", dependencies=administrar)
    def guardar_parametros(entrada: ParametrosEntrada, sesion: SesionActual):
        hacer(lambda: servicio.guardar_parametros(entrada.model_dump(), sesion.actor))
        return servicio.vista_parametros()

    # La clave privada se genera y queda en el servidor: ningún endpoint la devuelve.
    @app.get("/certificado", dependencies=administrar)
    def certificado():
        return servicio.estado_certificado()

    @app.post("/certificado/pedido", dependencies=administrar)
    def generar_pedido(sesion: SesionActual):
        csr = hacer(lambda: servicio.generar_pedido(sesion.actor))
        nombre, _ = servicio.pedido()
        return {"nombre": nombre, "csr_pem": csr, "estado": servicio.estado_certificado()}

    @app.get("/certificado/pedido", dependencies=administrar)
    def bajar_pedido():
        nombre, csr = hacer(servicio.pedido)
        return Response(csr, media_type="application/pkcs10",
                        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})

    @app.put("/certificado", dependencies=administrar)
    def cargar_certificado(entrada: CertificadoEntrada, sesion: SesionActual):
        return hacer(lambda: servicio.cargar_certificado(entrada.certificado_pem, sesion.actor))

    return app
