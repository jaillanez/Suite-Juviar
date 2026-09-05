"""apps/web — sitio público. Despliegue independiente, en DMZ.

Reglas que este proceso cumple estructuralmente (§4.3 de la Base Común,
extendidas al sitio público):
  1. No consulta la base interna. Sólo la base de la DMZ.
  2. Escribe únicamente en la bandeja de entrada; no lee datos de negocio.
  3. Vive en DMZ, sin ruta hacia el servidor de Santa Fe.
  4. Toda solicitud queda registrada con IP, agente y sello de tiempo.
  5. No expone consulta de ningún dato: el sitio es de una sola dirección.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from apps.web.catalogos import RepositorioCatalogos
from apps.web.config import Config
from apps.web.esquemas import SolicitudAceptada, SolicitudMuestra
from apps.web.repositorio import RepositorioBandeja

log = logging.getLogger("apps.web")

config = Config.desde_entorno()
app = FastAPI(title="Vitivinicola Argentina - sitio publico", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="apps/web/static"), name="static")
plantillas = Jinja2Templates(directory="apps/web/templates")

bandeja = RepositorioBandeja(config.dsn_dmz)
catalogos = RepositorioCatalogos(config.dsn_dmz)

_intentos: dict[str, list[datetime]] = defaultdict(list)


def _limite_alcanzado(ip: str) -> bool:
    ahora = datetime.now(UTC)
    corte = ahora - timedelta(hours=1)
    _intentos[ip] = [t for t in _intentos[ip] if t > corte]
    if len(_intentos[ip]) >= config.limite_por_hora:
        return True
    _intentos[ip].append(ahora)
    return False


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    respuesta = await call_next(request)
    respuesta.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "script-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'none'"
    )
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    respuesta.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return respuesta


@app.get("/", response_class=HTMLResponse)
@app.get("/es/", response_class=HTMLResponse)
@app.get("/en/", response_class=HTMLResponse)
def portada(request: Request) -> HTMLResponse:
    idioma = "en" if request.url.path.startswith("/en") else "es"
    token = token_urlsafe(24)
    respuesta = plantillas.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "idioma": idioma,
            "csrf_token": token,
            "lineas_producto": catalogos.lineas_producto(),
            "formatos_despacho": catalogos.formatos_despacho(),
            "certificaciones": catalogos.certificaciones(),
        },
    )
    respuesta.set_cookie(
        "csrf", token, httponly=False, secure=True, samesite="strict", max_age=7200
    )
    return respuesta


@app.post("/api/muestras", response_model=SolicitudAceptada)
def recibir_solicitud(solicitud: SolicitudMuestra, request: Request) -> SolicitudAceptada:
    ip = request.client.host if request.client else "desconocida"

    if request.headers.get("X-CSRF-Token") != request.cookies.get("csrf"):
        raise HTTPException(status_code=403, detail="token invalido")

    if _limite_alcanzado(ip):
        raise HTTPException(status_code=429, detail="demasiadas solicitudes")

    validos_producto = catalogos.codigos_validos("linea_producto")
    validos_formato = catalogos.codigos_validos("formato_despacho")
    validos_cert = catalogos.codigos_validos("certificacion")

    if solicitud.product_line not in validos_producto:
        raise HTTPException(status_code=422, detail="linea de producto desconocida")
    if solicitud.projected_volume.shipment_format not in validos_formato:
        raise HTTPException(status_code=422, detail="formato de despacho desconocido")
    if not set(solicitud.certifications_required) <= validos_cert:
        raise HTTPException(status_code=422, detail="certificacion desconocida")

    referencia = bandeja.proxima_referencia()
    bandeja.guardar(
        solicitud,
        referencia=referencia,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
        idioma="en" if request.headers.get("accept-language", "").startswith("en") else "es",
    )
    log.info("solicitud %s recibida desde %s", referencia, ip)
    return SolicitudAceptada(referencia=referencia)


@app.get("/salud")
def salud() -> JSONResponse:
    return JSONResponse({"estado": "ok", "entorno": config.entorno})
