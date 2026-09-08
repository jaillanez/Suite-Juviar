"""API del perfil depósito para la entrega de ropa de trabajo y EPP.

Forma parte del backend único. ``X-Legajo-Usuario`` es una declaración local
de identidad suplantable, no una sesión ni un autenticador. El perfil se
resuelve del lado servidor desde Parametría, pero parte de esa identidad no
autenticada hasta que ``plataforma/identidad`` esté operativo.
"""

import os
from base64 import b64decode
from datetime import date, datetime
from ipaddress import ip_address
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

from suite_juviar.plataforma.identidad.api.dependencias import SesionActual, exigir_permiso
from suite_juviar.plataforma.identidad.domain.acceso import (
    ActorOperativo,
    PerfilAcceso,
)

from ..domain.modelos_mvp import (
    ElementoEPP,
    ErrorDeEntrega,
    ItemCatalogo,
    LegajoInexistente,
    RequisitoEPP,
)
from ..infrastructure.catalogo_yaml import ErrorDeCatalogo
from ..mvp import Contenedor, construir

PLANTILLAS = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _es_loopback(valor: str) -> bool:
    limpio = valor.strip().removeprefix("[").removesuffix("]")
    if limpio.lower() == "localhost":
        return True
    try:
        return ip_address(limpio).is_loopback
    except ValueError:
        return False


def _host_es_local(valor: str) -> bool:
    return _es_loopback(urlsplit(f"//{valor.strip()}").hostname or "")


def _solicitud_es_exclusivamente_local(request: Request) -> bool:
    """Barrera de accidente para demos; no convierte el header en autenticación."""
    if request.client is None or not _es_loopback(request.client.host):
        return False
    reenviadas = request.headers.get("x-forwarded-for", "")
    if reenviadas and any(not _es_loopback(valor) for valor in reenviadas.split(",")):
        return False
    hosts = [request.headers.get("host", ""), request.headers.get("x-forwarded-host", "")]
    if any(valor and not _host_es_local(valor) for valor in hosts):
        return False
    for encabezado in ("origin", "referer"):
        valor = request.headers.get(encabezado)
        if valor and not _es_loopback(urlsplit(valor).hostname or ""):
            return False
    return True


class ItemEntrada(BaseModel):
    codigo: str = Field(min_length=1, max_length=30)
    item_codigo: str = Field(min_length=1, max_length=80)
    cantidad: int
    reclamo_calidad: str | None = None


class EntregaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legajo: str = Field(min_length=1, max_length=30)
    items: list[ItemEntrada] = Field(default_factory=list, max_length=50)
    metodo_firma: str = "TRAZO_TABLET"
    evidencia_firma: str = Field(default="", max_length=2_000_000)
    observaciones: str = Field(default="", max_length=1_000)
    id_cliente: str | None = Field(
        default=None,
        min_length=8,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    entregada_en: datetime | None = None
    actor_declarado: str | None = Field(default=None, min_length=1, max_length=30)
    circuito: str = Field(default="ESPONTANEA", min_length=1, max_length=20)
    motivo: str = Field(default="DESGASTE", min_length=1, max_length=30)


class StockEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disponible: int = Field(ge=0)
    minimo: int = Field(ge=0)


class ElementoCatalogoEntrada(BaseModel):
    producto: str
    tipo_modelo: str = ""
    marca: str = ""
    posee_certificacion: bool = False
    certificacion: str | None = None
    unidad: str = "unidad"
    vida_util_dias: int | None = None
    familia: str = "Otros"
    destino_declarado: str | None = None
    criterio_vida_util: str = ""


class ItemCatalogoEntrada(BaseModel):
    elemento_codigo: str
    marca: str
    modelo: str
    talle: str
    color: str


class ImportacionEntrada(BaseModel):
    contenido_base64: str


class RequisitoEntrada(BaseModel):
    codigo: str
    cantidad: int = Field(gt=0)
    frecuencia: str = "A_DEMANDA"
    temporada: str = "TODO_EL_ANIO"
    obligatorio: bool = True
    fundamento: str = ""


class MatrizEntrada(BaseModel):
    requisitos: list[RequisitoEntrada]


class MovimientoEntrada(BaseModel):
    cantidad: int
    tipo: str
    motivo: str = Field(min_length=1)


def crear_app(contenedor: Contenedor | None = None) -> FastAPI:
    c = contenedor or construir()
    app = FastAPI(
        title="Suite Juviar — Entrega de EPP",
        version="0.2.0-mvp",
        dependencies=[Depends(exigir_permiso("suite.acceder"))],
    )
    app.state.c = c

    def usuario_actual(
        request: Request,
        x_legajo_usuario: str | None = Header(default=None, alias="X-Legajo-Usuario"),
    ) -> ActorOperativo:
        if c.entorno != "prueba" and not _solicitud_es_exclusivamente_local(request):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "La identidad declarada sólo se admite desde loopback. "
                    "No exponga esta demo en una red compartida."
                ),
            )
        if not x_legajo_usuario:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Falta declarar el legajo del usuario.",
            )
        legajo = c.legajos.obtener(x_legajo_usuario)
        if legajo is None or not legajo.activo:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="El usuario no existe o está inactivo.",
            )
        perfil_codigo = c.perfiles_acceso.resolver(
            legajo.puesto_codigo,
            legajo.sector_codigo,
        )
        if perfil_codigo is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El puesto del usuario no tiene un perfil móvil habilitado.",
            )
        return ActorOperativo(
            legajo=legajo.legajo,
            nombre_completo=legajo.nombre_completo,
            empresa=legajo.empresa,
            perfil=PerfilAcceso(perfil_codigo),
        )

    def operador_deposito(
        usuario: Annotated[ActorOperativo, Depends(usuario_actual)],
    ) -> ActorOperativo:
        """Adapta la sesión al actor de dominio; la autorización vive en cada ruta."""
        return usuario

    UsuarioActual = Annotated[ActorOperativo, Depends(usuario_actual)]
    OperadorDeposito = Annotated[ActorOperativo, Depends(operador_deposito)]

    @app.exception_handler(ErrorDeEntrega)
    async def _rechazo(_request: Request, exc: ErrorDeEntrega) -> JSONResponse:
        codigo = 404 if isinstance(exc, LegajoInexistente) else 400
        return JSONResponse(status_code=codigo, content={"error": str(exc)})

    @app.get("/sesion", dependencies=[Depends(exigir_permiso("suite.acceder"))])
    def sesion(usuario: UsuarioActual) -> dict[str, str]:
        return {
            "legajo": usuario.legajo,
            "nombre_completo": usuario.nombre_completo,
            "empresa": usuario.empresa,
            "perfil": usuario.perfil.value,
        }

    @app.get("/estado", dependencies=[Depends(exigir_permiso("epp.catalogo.leer"))])
    def estado(sesion: SesionActual) -> dict[str, object]:
        return {
            "entorno": c.entorno,
            "persistencia": c.persistencia,
            "fuente_legajos": c.legajos.fuente,
            "modo_simulado": c.modo_simulado,
            "estado_matriz_epp": c.catalogo.estado_matriz,
            "estado_vida_util": c.catalogo.estado_vida_util,
            "estado_catalogo_items": c.catalogo.estado_items,
            "dueno_catalogo_items": c.catalogo.dueno_items,
            "estado_mapa_perfiles": c.perfiles_acceso.estado,
            "dueno_mapa_perfiles": c.perfiles_acceso.dueno_dato,
            "estado_stock": c.stock.estado,
            "dueno_stock": c.stock.dueno_dato,
            "canal_aviso_compras": "EMAIL",
            "email_compras_configurado": c.email_compras is not None,
            "transporte_email_configurado": bool(
                os.getenv("SJ_SMTP_HOST") and os.getenv("SJ_SMTP_REMITENTE")
            ),
            "metodos_firma": list(c.firma.metodos_habilitados),
            "actor": sesion.actor,
        }

    @app.get("/legajos", dependencies=[Depends(exigir_permiso("epp.entrega.operar"))])
    def buscar_legajos(
        _usuario: OperadorDeposito,
        q: str = "",
    ) -> list[dict[str, object]]:
        return [
            {
                "legajo": p.legajo,
                "nombre_completo": p.nombre_completo,
                "dni": p.dni,
                "puesto": p.puesto,
                "sector": p.sector,
                "empresa": p.empresa,
                "tipo_vinculo": p.tipo_vinculo,
            }
            for p in c.legajos.buscar(q)
        ]

    @app.get("/legajos/{numero}", dependencies=[Depends(exigir_permiso("epp.entrega.operar"))])
    def ver_legajo(
        numero: str,
        _usuario: OperadorDeposito,
    ) -> dict[str, object]:
        persona, requeridos, historial = c.consultar_legajo.ejecutar(numero)
        entregados = {l.codigo: e.fecha_entrega for e in historial for l in e.lineas}
        return {
            "cabecera": {
                "legajo": persona.legajo,
                "nombre_completo": persona.nombre_completo,
                "dni": persona.dni,
                "puesto": persona.puesto,
                "sector": persona.sector,
                "empresa": persona.empresa,
                "tipo_vinculo": persona.tipo_vinculo,
                "fuente": c.legajos.fuente,
            },
            "epp_requerido": [
                {
                    "codigo": elemento.codigo,
                    "producto": elemento.producto,
                    "tipo_modelo": elemento.tipo_modelo,
                    "marca": elemento.marca,
                    "posee_certificacion": elemento.posee_certificacion,
                    "certificacion": elemento.certificacion,
                    "unidad": elemento.unidad,
                    "cantidad_sugerida": requisito.cantidad,
                    "frecuencia": requisito.frecuencia,
                    "temporada": requisito.temporada,
                    "obligatorio": requisito.obligatorio,
                    "fundamento": requisito.fundamento,
                    "origen": requisito.origen,
                    "ultima_entrega": (
                        entregados[elemento.codigo].isoformat()
                        if elemento.codigo in entregados
                        else None
                    ),
                    "items": [
                        {
                            "codigo_interno": item.codigo_interno,
                            "marca": item.marca,
                            "modelo": item.modelo,
                            "talle": item.talle,
                            "color": item.color,
                            "estado": item.estado,
                        }
                        for item in c.catalogo.items_de(elemento.codigo)
                    ],
                }
                for requisito, elemento in requeridos
            ],
            "matriz_sector_definida": c.catalogo.sector_definido(persona.sector_codigo),
            "historial": [
                {
                    "id": entrega.id,
                    "fecha": entrega.fecha_entrega.isoformat(),
                    "items": entrega.cantidad_items,
                    "usuario": entrega.usuario_deposito,
                    "circuito": entrega.circuito,
                    "motivo": entrega.motivo,
                }
                for entrega in historial
            ],
        }

    @app.get("/entregas-programadas", dependencies=[Depends(exigir_permiso("epp.entrega.operar"))])
    def entregas_programadas(
        fecha: date,
        _usuario: OperadorDeposito,
        temporada: str,
        sector: str | None = None,
    ) -> list[dict[str, object]]:
        return [
            {
                "fecha": plan.fecha.isoformat(),
                "temporada": plan.temporada,
                "legajo": plan.trabajador.legajo,
                "nombre_completo": plan.trabajador.nombre_completo,
                "puesto": plan.trabajador.puesto,
                "sector_codigo": plan.trabajador.sector_codigo,
                "sector": plan.trabajador.sector,
                "elementos": [
                    {
                        "codigo": requisito.codigo,
                        "cantidad": requisito.cantidad,
                        "origen": requisito.origen,
                    }
                    for requisito in plan.requisitos
                ],
                "fuente_legajo": c.legajos.fuente,
                "estado_matriz": c.catalogo.estado_matriz,
            }
            for plan in c.planificar_entregas.ejecutar(temporada, fecha, sector)
        ]

    @app.get("/catalogo", dependencies=[Depends(exigir_permiso("epp.catalogo.leer"))])
    def catalogo() -> list[dict[str, object]]:
        return [
            {
                "codigo": elemento.codigo,
                "producto": elemento.producto,
                "tipo_modelo": elemento.tipo_modelo,
                "marca": elemento.marca,
                "posee_certificacion": elemento.posee_certificacion,
                "certificacion": elemento.certificacion,
                "unidad": elemento.unidad,
                "familia": elemento.familia,
                "destino_declarado": elemento.destino_declarado,
                "vida_util_dias": elemento.vida_util_dias,
                "criterio_vida_util": elemento.criterio_vida_util,
                "activo": elemento.activo,
                "simulado": any(item.codigo_interno.startswith("SIM-") for item in c.catalogo.items_de(elemento.codigo)),
                "items": [item.__dict__ for item in c.catalogo.items_de(elemento.codigo)],
            }
            for elemento in c.catalogo.listar_elementos()
        ]

    @app.post("/catalogo/elementos/{codigo}", dependencies=[Depends(exigir_permiso("epp.catalogo.editar"))])
    def alta_elemento(codigo: str, entrada: ElementoCatalogoEntrada):
        return c.catalogo.guardar_elemento(ElementoEPP(codigo=codigo, activo=True, **entrada.model_dump()))

    @app.put("/catalogo/elementos/{codigo}", dependencies=[Depends(exigir_permiso("epp.catalogo.editar"))])
    def editar_elemento(codigo: str, entrada: ElementoCatalogoEntrada):
        if c.catalogo.obtener_elemento(codigo) is None:
            raise HTTPException(404, "Elemento inexistente")
        return c.catalogo.guardar_elemento(ElementoEPP(codigo=codigo, activo=True, **entrada.model_dump()))

    @app.delete("/catalogo/elementos/{codigo}", dependencies=[Depends(exigir_permiso("epp.catalogo.editar"))])
    def baja_elemento(codigo: str):
        try:
            return c.catalogo.baja_elemento(codigo)
        except ErrorDeCatalogo as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/catalogo/items/{codigo}", dependencies=[Depends(exigir_permiso("epp.catalogo.editar"))])
    def alta_item(codigo: str, entrada: ItemCatalogoEntrada):
        try:
            return c.catalogo.guardar_item(ItemCatalogo(codigo_interno=codigo, estado="ACTIVO", activo=True, **entrada.model_dump()))
        except ErrorDeCatalogo as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.put("/catalogo/items/{codigo}", dependencies=[Depends(exigir_permiso("epp.catalogo.editar"))])
    def editar_item(codigo: str, entrada: ItemCatalogoEntrada):
        try:
            return c.catalogo.guardar_item(ItemCatalogo(codigo_interno=codigo, estado="ACTIVO", activo=True, **entrada.model_dump()))
        except ErrorDeCatalogo as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.delete("/catalogo/items/{codigo}", dependencies=[Depends(exigir_permiso("epp.catalogo.editar"))])
    def baja_item(codigo: str):
        try:
            return c.catalogo.baja_item(codigo)
        except ErrorDeCatalogo as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/catalogo/importaciones", dependencies=[Depends(exigir_permiso("epp.catalogo.editar"))])
    def previsualizar_importacion(entrada: ImportacionEntrada):
        try:
            return c.importaciones_catalogo.previsualizar(b64decode(entrada.contenido_base64, validate=True))
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/catalogo/importaciones/{identificador}/aplicar", dependencies=[Depends(exigir_permiso("epp.catalogo.editar"))])
    def aplicar_importacion(identificador: str):
        try:
            return c.importaciones_catalogo.aplicar(identificador)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/matriz/estado", dependencies=[Depends(exigir_permiso("epp.catalogo.leer"))])
    def estado_matriz():
        return {"estado": c.catalogo.estado_matriz, "validacion": c.catalogo.validacion_matriz, "historial": c.catalogo.historial_matriz}

    @app.get("/matriz/puestos/{puesto}", dependencies=[Depends(exigir_permiso("epp.catalogo.leer"))])
    def matriz_puesto(puesto: str):
        return c.catalogo.matriz_puesto(puesto)

    @app.put("/matriz/puestos/{puesto}", dependencies=[Depends(exigir_permiso("epp.matriz.editar"))])
    def editar_matriz(puesto: str, entrada: MatrizEntrada, sesion: SesionActual):
        requisitos = [RequisitoEPP(**r.model_dump(), origen="PUESTO") for r in entrada.requisitos]
        try:
            return c.catalogo.guardar_matriz_puesto(puesto, requisitos, sesion.actor)
        except ErrorDeCatalogo as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/matriz/validar", dependencies=[Depends(exigir_permiso("epp.matriz.editar"))])
    def validar_matriz(sesion: SesionActual):
        return c.catalogo.validar_matriz(sesion.actor)

    @app.get("/stock", dependencies=[Depends(exigir_permiso("epp.stock.leer"))])
    def stock() -> list[dict[str, object]]:
        return [
            {
                "item_codigo": item.item_codigo,
                "disponible": item.disponible,
                "minimo": item.minimo,
                "estado": item.estado,
            }
            for item in c.stock.listar()
        ]

    @app.put("/stock/{item_codigo}", dependencies=[Depends(exigir_permiso("epp.stock.editar"))])
    def configurar_stock(
        item_codigo: str,
        entrada: StockEntrada,
        sesion: SesionActual,
    ) -> dict[str, object]:
        item = c.stock.configurar(item_codigo, entrada.disponible, entrada.minimo)
        c.bitacora.registrar(
            evento="STOCK_EPP_CONFIGURADO",
            usuario=sesion.actor,
            detalle={
                "item_codigo": item.item_codigo,
                "disponible": item.disponible,
                "minimo": item.minimo,
            },
        )
        return {
            "item_codigo": item.item_codigo,
            "disponible": item.disponible,
            "minimo": item.minimo,
            "estado": item.estado,
        }

    @app.get("/stock/alertas", dependencies=[Depends(exigir_permiso("epp.stock.leer"))])
    def alertas_stock() -> list[dict[str, object]]:
        return [
            {
                **aviso,
                "canal": "EMAIL",
                "destinatario": c.email_compras,
                "estado_envio": "PENDIENTE_TRANSPORTE",
            }
            for aviso in c.stock.alertas_pendientes()
        ]

    @app.get("/stock/{item_codigo}/movimientos", dependencies=[Depends(exigir_permiso("epp.stock.leer"))])
    def movimientos_stock(item_codigo: str):
        return c.stock.movimientos(item_codigo)

    @app.post("/stock/{item_codigo}/movimientos", dependencies=[Depends(exigir_permiso("epp.stock.editar"))])
    def mover_stock(item_codigo: str, entrada: MovimientoEntrada, sesion: SesionActual):
        return c.stock.registrar_movimiento(item_codigo, entrada.cantidad, entrada.tipo, entrada.motivo, sesion.actor)

    @app.get("/avisos-compras", dependencies=[Depends(exigir_permiso("epp.aviso.gestionar"))])
    def avisos_compras():
        return c.stock.avisos()

    @app.post("/avisos-compras/{aviso_id}/reenviar", dependencies=[Depends(exigir_permiso("epp.aviso.gestionar"))])
    def reenviar_aviso(aviso_id: int):
        try:
            return c.stock.reenviar_alerta(aviso_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/entregas", dependencies=[Depends(exigir_permiso("epp.entrega.operar"))])
    def registrar(
        entrada: EntregaEntrada,
        usuario: OperadorDeposito,
    ) -> dict[str, object]:
        entrega = c.registrar_entrega.ejecutar(
            numero_legajo=entrada.legajo,
            items=[
                {
                    "codigo": item.codigo,
                    "item_codigo": item.item_codigo,
                    "cantidad": item.cantidad,
                    "reclamo_calidad": item.reclamo_calidad,
                }
                for item in entrada.items
            ],
            metodo_firma=entrada.metodo_firma,
            evidencia_firma=entrada.evidencia_firma,
            usuario_deposito=usuario.legajo,
            observaciones=entrada.observaciones,
            id_entrega=entrada.id_cliente,
            entregada_en=entrada.entregada_en,
            circuito=entrada.circuito,
            motivo=entrada.motivo,
        )
        documento = c.obtener_constancia_pdf.ejecutar(entrega.id)
        if documento is None:
            raise HTTPException(status_code=500, detail="No se pudo conservar la constancia.")
        return {
            "id": entrega.id,
            "legajo": entrega.legajo.legajo,
            "fecha": entrega.fecha_entrega.isoformat(),
            "items": entrega.cantidad_items,
            "firma_simulada": entrega.firma_trabajador.simulada,
            "constancia": f"/api/v1/rrhh-epp/constancias/{entrega.id}.pdf",
            "version_constancia": documento.version,
            "anula_a": documento.anula_a,
        }

    @app.get("/entregas", dependencies=[Depends(exigir_permiso("epp.entrega.leer"))])
    def buscar_entregas(desde: date, hasta: date, legajo: str | None = None, sector: str | None = None, item: str | None = None):
        entregas = c.entregas.listar_periodo(desde, hasta)
        return [
            {"id": e.id, "legajo": e.legajo.legajo, "persona": e.legajo.nombre_completo,
             "sector": e.legajo.sector, "fecha": e.fecha_entrega, "circuito": e.circuito,
             "motivo": e.motivo, "lineas": [linea.__dict__ for linea in e.lineas]}
            for e in entregas
            if (not legajo or e.legajo.legajo == legajo)
            and (not sector or e.legajo.sector == sector)
            and (not item or any(l.item_codigo == item for l in e.lineas))
        ]

    @app.get("/entregas/{id_entrega}", dependencies=[Depends(exigir_permiso("epp.entrega.leer"))])
    def ficha_entrega(id_entrega: str):
        e = c.entregas.obtener(id_entrega)
        if e is None:
            raise HTTPException(404, "Entrega inexistente")
        documento = c.obtener_constancia_pdf.ejecutar(id_entrega)
        versiones = []
        while documento is not None:
            versiones.append({"id_entrega": documento.id_entrega,
                              "version": documento.version, "sha256": documento.sha256,
                              "firmado": documento.firmado, "anula_a": documento.anula_a,
                              "archivo": f"/api/v1/rrhh-epp/constancias/{documento.id_entrega}.pdf"})
            documento = (c.obtener_constancia_pdf.ejecutar(documento.anula_a)
                         if documento.anula_a else None)
        return {"id": e.id, "legajo": e.legajo.__dict__, "fecha": e.fecha_entrega,
                "motivo": e.motivo, "lineas": [l.__dict__ for l in e.lineas],
                "constancias": versiones}

    @app.get("/constancias/{id_entrega}.pdf", dependencies=[Depends(exigir_permiso("epp.entrega.leer"))])
    def constancia_pdf(
        id_entrega: str,
    ) -> Response:
        documento = c.obtener_constancia_pdf.ejecutar(id_entrega)
        if documento is None:
            raise HTTPException(status_code=404, detail="No existe esa constancia.")
        return Response(
            content=documento.contenido,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="constancia-{id_entrega}.pdf"',
                "X-Contenido-SHA256": documento.sha256,
                "X-Documento-Simulado": "SI" if documento.simulado else "NO",
            },
        )

    @app.get("/constancias/{id_entrega}", response_class=HTMLResponse, dependencies=[Depends(exigir_permiso("epp.entrega.leer"))])
    def constancia(
        request: Request,
        id_entrega: str,
    ) -> HTMLResponse:
        entrega = c.entregas.obtener(id_entrega)
        if entrega is None:
            raise HTTPException(status_code=404, detail="No existe esa constancia.")
        return PLANTILLAS.TemplateResponse(
            request=request,
            name="constancia.html",
            context={"e": entrega, "modo_simulado": c.modo_simulado},
        )

    @app.get("/bitacora", dependencies=[Depends(exigir_permiso("epp.entrega.leer"))])
    def bitacora(
        n: int = 50,
    ) -> list[dict]:
        return c.bitacora.ultimos(n)

    @app.get("/alertas-catalogo", dependencies=[Depends(exigir_permiso("epp.catalogo.leer"))])
    def alertas_catalogo() -> dict[str, object]:
        alertas = c.catalogo.alertas()
        return {
            "estado_vida_util": c.catalogo.estado_vida_util,
            "cantidad": len(alertas),
            "alertas": alertas,
        }

    @app.get("/matriz", response_class=HTMLResponse, dependencies=[Depends(exigir_permiso("epp.catalogo.leer"))])
    def revisar_matriz(
        request: Request,
    ) -> HTMLResponse:
        """Revisión de sólo lectura; aprobar exige identidad real."""
        senales = ("PROPUESTA", "CONFIRMAR", "VERIFICAR", "REVISAR", "FALTA")
        alertas_catalogo = c.catalogo.alertas()
        sectores: list[dict[str, object]] = []
        total = 0
        a_revisar = 0
        por_origen: dict[str, int] = {}
        for codigo in c.catalogo.sectores_conocidos:
            lineas: list[dict[str, object]] = []
            for requisito in c.catalogo.requisitos_de(codigo, ""):
                elemento = c.catalogo.obtener_elemento(requisito.codigo)
                if elemento is None:  # la carga del catálogo ya lo impide
                    continue
                revisar = any(senal in requisito.fundamento.upper() for senal in senales)
                etiqueta = requisito.fundamento.split(" ")[0]
                por_origen[etiqueta] = por_origen.get(etiqueta, 0) + 1
                if "RD" in etiqueta:
                    por_origen["RD 068/11"] = por_origen.get("RD 068/11", 0) + 1
                total += 1
                a_revisar += int(revisar)
                lineas.append(
                    {
                        "codigo": requisito.codigo,
                        "producto": elemento.producto,
                        "tipo_modelo": elemento.tipo_modelo,
                        "marca": elemento.marca,
                        "cantidad": requisito.cantidad,
                        "obligatorio": requisito.obligatorio,
                        "frecuencia": requisito.frecuencia,
                        "temporada": requisito.temporada,
                        "fundamento": requisito.fundamento,
                        "origen": requisito.origen,
                        "revisar": revisar,
                    }
                )
            sectores.append(
                {
                    "codigo": codigo,
                    "nombre": c.catalogo.nombre_sector(codigo),
                    "lineas": lineas,
                    "aplica_base": c.catalogo.aplica_base(codigo),
                }
            )
        return PLANTILLAS.TemplateResponse(
            request=request,
            name="matriz.html",
            context={
                "sectores": sectores,
                "total_lineas": total,
                "a_revisar": a_revisar,
                "por_origen": por_origen,
                "version_norma": c.catalogo.version_norma,
                "cantidad_alertas_catalogo": len(alertas_catalogo),
                "estado_vida_util": c.catalogo.estado_vida_util,
            },
        )

    return app
