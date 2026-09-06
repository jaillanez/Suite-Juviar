"""API del perfil depósito para la entrega de ropa de trabajo y EPP.

Forma parte del backend único. ``X-Legajo-Usuario`` es una declaración local
de identidad suplantable, no una sesión ni un autenticador. El perfil se
resuelve del lado servidor desde Parametría, pero parte de esa identidad no
autenticada hasta que ``plataforma/identidad`` esté operativo.
"""

from datetime import date, datetime
from ipaddress import ip_address
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

from suite_juviar.plataforma.identidad.domain.acceso import (
    ActorOperativo,
    PerfilAcceso,
)

from ..domain.modelos_mvp import ErrorDeEntrega, LegajoInexistente
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


def crear_app(contenedor: Contenedor | None = None) -> FastAPI:
    c = contenedor or construir()
    app = FastAPI(title="Suite Juviar — Entrega de EPP", version="0.2.0-mvp")
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
        if usuario.perfil is not PerfilAcceso.DEPOSITO:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="La entrega de EPP requiere el perfil depósito.",
            )
        return usuario

    UsuarioActual = Annotated[ActorOperativo, Depends(usuario_actual)]
    OperadorDeposito = Annotated[ActorOperativo, Depends(operador_deposito)]

    @app.exception_handler(ErrorDeEntrega)
    async def _rechazo(_request: Request, exc: ErrorDeEntrega) -> JSONResponse:
        codigo = 404 if isinstance(exc, LegajoInexistente) else 400
        return JSONResponse(status_code=codigo, content={"error": str(exc)})

    @app.get("/sesion")
    def sesion(usuario: UsuarioActual) -> dict[str, str]:
        return {
            "legajo": usuario.legajo,
            "nombre_completo": usuario.nombre_completo,
            "empresa": usuario.empresa,
            "perfil": usuario.perfil.value,
        }

    @app.get("/estado")
    def estado(usuario: UsuarioActual) -> dict[str, object]:
        return {
            "entorno": c.entorno,
            "fuente_legajos": c.legajos.fuente,
            "modo_simulado": c.modo_simulado,
            "estado_matriz_epp": c.catalogo.estado_matriz,
            "estado_vida_util": c.catalogo.estado_vida_util,
            "estado_catalogo_items": c.catalogo.estado_items,
            "dueno_catalogo_items": c.catalogo.dueno_items,
            "estado_mapa_perfiles": c.perfiles_acceso.estado,
            "dueno_mapa_perfiles": c.perfiles_acceso.dueno_dato,
            "metodos_firma": list(c.firma.metodos_habilitados),
            "perfil": usuario.perfil.value,
        }

    @app.get("/legajos")
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

    @app.get("/legajos/{numero}")
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

    @app.get("/entregas-programadas")
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

    @app.get("/catalogo")
    def catalogo(_usuario: OperadorDeposito) -> list[dict[str, object]]:
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
            }
            for elemento in c.catalogo.listar_elementos()
        ]

    @app.post("/entregas")
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
        return {
            "id": entrega.id,
            "legajo": entrega.legajo.legajo,
            "fecha": entrega.fecha_entrega.isoformat(),
            "items": entrega.cantidad_items,
            "firma_simulada": entrega.firma_trabajador.simulada,
            "constancia": f"/api/v1/rrhh-epp/constancias/{entrega.id}.pdf",
        }

    @app.get("/constancias/{id_entrega}.pdf")
    def constancia_pdf(
        id_entrega: str,
        _usuario: OperadorDeposito,
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

    @app.get("/constancias/{id_entrega}", response_class=HTMLResponse)
    def constancia(
        request: Request,
        id_entrega: str,
        _usuario: OperadorDeposito,
    ) -> HTMLResponse:
        entrega = c.entregas.obtener(id_entrega)
        if entrega is None:
            raise HTTPException(status_code=404, detail="No existe esa constancia.")
        return PLANTILLAS.TemplateResponse(
            request=request,
            name="constancia.html",
            context={"e": entrega, "modo_simulado": c.modo_simulado},
        )

    @app.get("/bitacora")
    def bitacora(
        _usuario: OperadorDeposito,
        n: int = 50,
    ) -> list[dict]:
        return c.bitacora.ultimos(n)

    @app.get("/alertas-catalogo")
    def alertas_catalogo(_usuario: OperadorDeposito) -> dict[str, object]:
        alertas = c.catalogo.alertas()
        return {
            "estado_vida_util": c.catalogo.estado_vida_util,
            "cantidad": len(alertas),
            "alertas": alertas,
        }

    @app.get("/matriz", response_class=HTMLResponse)
    def revisar_matriz(
        request: Request,
        _usuario: OperadorDeposito,
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
