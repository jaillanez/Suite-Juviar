from __future__ import annotations

import hashlib
import os
import time
from base64 import b64decode, b64encode
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import (
    SesionActual,
    exigir_identidad_configurada,
    exigir_permiso,
)

from ..application.correo import CorreoRRHH
from ..application.datos_cv import combinar, extraccion_combinada, motivo_faltantes
from ..application.datos_faltantes import datos_faltantes
from ..application.extraccion import ExtraerDatosCV
from ..application.genero import FEMENINO, MASCULINO, genero_de
from ..application.ingesta import IngestarCVs
from ..application.lectura_ia import LeerCVsConIA
from ..application.ranking import EvaluarBusqueda, ordenar_resultados
from ..application.whatsapp import IncorporarCVWhatsapp
from ..domain.modelos import (
    Busqueda,
    ConfirmacionCampo,
    ConsultaOriginal,
    CVOriginal,
    OrigenCV,
    PerfilBusqueda,
)
from ..infrastructure import ia_deepseek
from ..infrastructure.cifrado import CifradorAESGCM
from ..infrastructure.correo_gmail import (
    BandejaGmailIMAP,
    ErrorCorreo,
    desde_para,
    enviar_por_gmail,
)
from ..infrastructure.extraccion_pdf import (
    CamposPorReglasProvisorias,
    TextoPDF,
    paginas_png,
    tipo_imagen,
)
from ..infrastructure.lectura_en_fondo import ColaLecturaCV, compartida
from ..infrastructure.sqlite import (
    ExtraccionesSQLite,
    OriginalesSQLite,
    busquedas_sqlite,
    consultas_ia_sqlite,
    correo_rrhh_sqlite,
    estados_cv_sqlite,
    fichas_ia_sqlite,
    historial_estados_sqlite,
    lecturas_ia_errores_sqlite,
)


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


class PedidoEntrada(BaseModel):
    pedido: str = Field(min_length=5, max_length=1500)
    incluir_marcados: bool = False
    desde: date | None = None
    hasta: date | None = None


ZONA = ZoneInfo("America/Argentina/San_Juan")


def _dia_de_carga(original: CVOriginal) -> date:
    return original.incorporado_en.astimezone(ZONA).date()


def _periodo(desde: date | None, hasta: date | None):
    """Filtro por fecha de carga del CV en la plataforma (Desde / Hasta, ambos incluidos)."""
    if desde and hasta and desde > hasta:
        raise HTTPException(400, "La fecha «Desde» no puede ser posterior a «Hasta».")
    return lambda original: (desde is None or _dia_de_carga(original) >= desde) and (
        hasta is None or _dia_de_carga(original) <= hasta)


ESTADOS_CV = {"DISPONIBLE", "CONTRATADO", "NO_CONVOCAR"}


class EstadoEntrada(BaseModel):
    estado: str
    motivo: str = Field(default="", max_length=500)


def ia_externa_permitida(entorno: str) -> bool:
    """Mandar CV a DeepSeek saca datos personales de la empresa: en producción sólo con autorización
    expresa en la configuración del servidor. Vale igual para la lectura a pedido y la automática."""
    return entorno.lower() not in {"produccion", "production", "prod"} or (
        os.getenv("SJ_IA_EXTERNA_AUTORIZADA", "").strip().lower() in {"1", "true", "si"}
    )


def lectura_cvs(ruta_base: str, entorno: str) -> tuple[LeerCVsConIA, ColaLecturaCV]:
    """La lectura en segundo plano (reglas + OCR, y IA si está autorizada), una sola por base de datos."""
    def crear() -> tuple[LeerCVsConIA, ColaLecturaCV]:
        originales = OriginalesSQLite(ruta_base)
        extracciones = ExtraccionesSQLite(ruta_base)
        texto = TextoPDF()
        servicio = LeerCVsConIA(
            originales, extracciones,
            ExtraerDatosCV(originales, extracciones, texto, CamposPorReglasProvisorias()),
            fichas_ia_sqlite(ruta_base), lecturas_ia_errores_sqlite(ruta_base),
            # A la IA va la capa de texto del PDF; si no la tiene (foto, escaneo), la imagen. Nunca el OCR.
            leer=lambda cv: ia_deepseek.leer_cv(cv.nombre_archivo, cv.contenido, texto.capa_texto(cv.contenido)),
            permitida=lambda: ia_externa_permitida(entorno) and ia_deepseek.disponible(),
            dormir=time.sleep,
        )
        return servicio, ColaLecturaCV(servicio.procesar)

    return compartida(str(Path(ruta_base).resolve()), crear)


def _al_incorporar(ruta_base: str, entorno: str):
    servicio, cola = lectura_cvs(ruta_base, entorno)

    def encolar(cv_id: str) -> None:
        if servicio.permitida():
            cola.encolar(cv_id)

    return encolar


def crear_router(perfiles, entorno: str = "prueba", ruta_base: str = "datos/modulos.sqlite3") -> APIRouter:
    exigir_identidad_configurada(entorno)
    app = APIRouter(dependencies=[Depends(exigir_permiso("seleccion.gestionar"))])
    originales = OriginalesSQLite(ruta_base)
    extracciones = ExtraccionesSQLite(ruta_base)
    extraer = ExtraerDatosCV(originales, extracciones, TextoPDF(), CamposPorReglasProvisorias())
    evaluar = EvaluarBusqueda(perfiles)
    busquedas = busquedas_sqlite(ruta_base)
    fichas_ia = fichas_ia_sqlite(ruta_base)
    consultas_ia = consultas_ia_sqlite(ruta_base)
    estados = estados_cv_sqlite(ruta_base)
    historial_estados = historial_estados_sqlite(ruta_base)
    lectura, cola = lectura_cvs(ruta_base, entorno)

    def estado_de(cv_id: str) -> dict[str, object]:
        return estados.get(cv_id) or {"estado": "DISPONIBLE"}

    def exigir_ia() -> None:
        if not ia_externa_permitida(entorno):
            raise HTTPException(409, "La lectura con IA externa no está autorizada en este servidor.")
        if not ia_deepseek.disponible():
            raise HTTPException(503, "Falta configurar la clave de DeepSeek en el servidor.")

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
                if lectura.permitida():
                    cola.encolar(digest)  # la IA lee en segundo plano; la carga no la espera
            ids.append(digest)
        return {"incorporados": ids, "marca": "DATOS SIMULADOS — SIN VALIDEZ"}

    def estado_lectura(cv_id: str) -> str:
        return cola.estado(cv_id) or lectura.estado(cv_id)

    def vista(original: CVOriginal, extraccion, confirmaciones=()) -> dict[str, object]:
        """Lo que se muestra de un CV: lo de la IA y, si la IA no lo encontró, lo de las reglas."""
        ficha = fichas_ia.get(original.id)
        datos = combinar(extraccion, ficha, confirmaciones)
        combinada = extraccion_combinada(extraccion, datos, original.id)
        estado_ia = estado_lectura(original.id)
        return {
            "datos": datos, "combinada": combinada, "ficha": ficha,
            "publico": {
                "datos_faltantes": datos_faltantes([d["nombre"] for d in datos]),
                "motivo_faltantes": motivo_faltantes(estado_ia),
                "lectura_ia": estado_ia,
                "texto_leido": bool(extraccion and extraccion.estado != "SIN_TEXTO"),
                **genero_de(ficha),
                "cargado_en": original.incorporado_en,
            },
        }

    @app.get("/cvs")
    def listar_cvs(busqueda_id: str | None = None, desde: date | None = None, hasta: date | None = None):
        busqueda = busquedas.get(busqueda_id) if busqueda_id else None
        en_periodo = _periodo(desde, hasta)
        filas = []
        for original in originales.listar_originales():
            if not en_periodo(original):
                continue
            extraccion = extracciones.obtener_extraccion(original.id)
            cv = vista(original, extraccion, extracciones.confirmaciones(original.id))
            combinada = cv["combinada"]
            resultado = evaluar.ejecutar(busqueda, combinada) if busqueda and extraccion else None
            filas.append({
                "id": original.id, "nombre": original.nombre_archivo,
                "requiere_revision": combinada.requiere_revision,
                "campos": cv["datos"],
                "campos_pendientes": list(combinada.campos_pendientes),
                "resultado": resultado,
                "estado": estado_de(original.id),
                **cv["publico"],
            })
        if busqueda:
            por_id = {fila["id"]: fila for fila in filas}
            ordenados = ordenar_resultados([fila["resultado"] for fila in filas if fila["resultado"]])
            return [por_id[resultado.id_original] for resultado in ordenados]
        return filas

    @app.get("/revision")
    def revision(desde: date | None = None, hasta: date | None = None):
        return [fila for fila in listar_cvs(None, desde, hasta) if fila["requiere_revision"]]

    @app.get("/cvs/{cv_id}")
    def ficha_cv(cv_id: str, busqueda_id: str | None = None):
        original = originales.obtener_original(cv_id)
        if original is None:
            raise HTTPException(404, "CV inexistente")
        extraccion = extracciones.obtener_extraccion(cv_id)
        # Abrir un CV que la IA todavía no leyó lo manda a leer (si la IA está autorizada).
        if extraccion is None or (cola.estado(cv_id) is None and lectura.necesita_ia(cv_id)):
            cola.encolar(cv_id, releer_reglas=extraccion is None)
        busqueda = busquedas.get(busqueda_id) if busqueda_id else None
        confirmaciones = extracciones.confirmaciones(cv_id)
        cv = vista(original, extraccion, confirmaciones)
        return {
            "id": cv_id,
            "nombre": original.nombre_archivo,
            "tipo": "imagen" if tipo_imagen(original.contenido) else "pdf",
            "campos": cv["datos"],
            "pendientes": list(cv["combinada"].campos_pendientes),
            "confirmaciones": confirmaciones,
            "ficha_ia": cv["ficha"],
            "error_ia": lectura.error(cv_id),
            "estado": estado_de(cv_id),
            "historial_estado": [h for h in historial_estados if h["cv_id"] == cv_id],
            "resultado": evaluar.ejecutar(busqueda, cv["combinada"]) if busqueda else None,
            **cv["publico"],
            "marca": "DATOS SIMULADOS — SIN VALIDEZ",
        }

    @app.post("/cvs/{cv_id}/releer", status_code=202)
    def releer_cv(cv_id: str):
        """Vuelve a leer este CV en segundo plano: reglas + OCR y, si está autorizada, la IA."""
        if originales.obtener_original(cv_id) is None:
            raise HTTPException(404, "CV inexistente")
        cola.encolar(cv_id, releer_reglas=True)
        return {"lectura_ia": estado_lectura(cv_id)}

    @app.post("/ia/releer", status_code=202)
    def releer_todos():
        """Reproceso de los CV ya cargados: los que no tienen ficha de IA (o una vieja incompleta) y los
        que las reglas dejaron con datos sin leer."""
        encolados = 0
        for original in originales.listar_originales():
            reglas = lectura.necesita_reglas(original.id)
            if (reglas or lectura.necesita_ia(original.id, incluir_errores=True)) and cola.encolar(
                    original.id, releer_reglas=reglas):
                encolados += 1
        return {"encolados": encolados, **cola.progreso()}

    @app.get("/cvs/{cv_id}/miniatura")
    def miniatura(cv_id: str):
        """Primera página del PDF como imagen chica, para la vista del detalle."""
        cv = originales.obtener_original(cv_id)
        if cv is None:
            raise HTTPException(404, "CV inexistente")
        if tipo_imagen(cv.contenido):
            raise HTTPException(400, "El currículum ya es una imagen.")
        paginas = paginas_png(cv.contenido, 1, 1.0)
        if not paginas:
            raise HTTPException(422, "No se pudo dibujar la primera página del PDF.")
        return {"contenido_base64": b64encode(paginas[0]).decode(), "paginas": _paginas(cv.contenido)}

    @app.put("/cvs/{cv_id}/campos/{campo}/confirmacion")
    def confirmar_campo(
        cv_id: str,
        campo: str,
        entrada: ConfirmacionEntrada,
        sesion: SesionActual,
    ):
        original = originales.obtener_original(cv_id)
        if original is None:
            raise HTTPException(404, "CV inexistente")
        datos = vista(original, extracciones.obtener_extraccion(cv_id))["datos"]
        if not any(dato["nombre"] == campo for dato in datos):
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

    @app.get("/ia/estado")
    def estado_ia():
        ids = [o.id for o in originales.listar_originales()]
        leidos = sum(1 for cv_id in ids if cv_id in fichas_ia)
        return {"disponible": lectura.permitida(), "total": len(ids), "leidos": leidos,
                "con_error": sum(1 for cv_id in ids if lectura.estado(cv_id) == "ERROR"), **cola.progreso()}

    @app.get("/ia/fichas")
    def fichas():
        return {cv_id: ficha for cv_id, ficha in fichas_ia.items()}

    @app.post("/cvs/{cv_id}/leer-ia")
    def leer_con_ia(cv_id: str, sesion: SesionActual):
        exigir_ia()
        try:
            return lectura.leer_ahora(cv_id, sesion.actor)
        except LookupError as exc:
            raise HTTPException(404, "CV inexistente") from exc
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc

    def genero_para_ia(ficha: dict[str, object]) -> str | None:
        dato = genero_de(ficha)
        if not dato["genero"]:
            return None
        texto = {FEMENINO: "femenino", MASCULINO: "masculino"}.get(dato["genero"], "otro")
        return texto if dato["origen"] == "CV" else f"{texto} (deducido del nombre)"

    @app.post("/ia/buscar")
    def buscar_con_ia(entrada: PedidoEntrada, sesion: SesionActual):
        exigir_ia()
        en_periodo = _periodo(entrada.desde, entrada.hasta)
        disponibles = {o.id: o for o in originales.listar_originales() if en_periodo(o)}
        leidas = {
            cv_id: {**f, "genero": genero_para_ia(f)} for cv_id, f in fichas_ia.items()
            if cv_id in disponibles
            and (entrada.incluir_marcados or estado_de(cv_id)["estado"] == "DISPONIBLE")
        }
        try:
            candidatos = ia_deepseek.buscar_candidatos(entrada.pedido.strip(), leidas)
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc
        consultas_ia.append({"actor": sesion.actor, "momento": datetime.now(UTC).isoformat(),
                             "pedido": entrada.pedido.strip(), "candidatos": len(candidatos)})
        return {
            "pedido": entrada.pedido.strip(),
            "sin_leer": sum(1 for cv_id in disponibles if cv_id not in fichas_ia),
            "marcados_excluidos": 0 if entrada.incluir_marcados else sum(
                1 for cv_id in disponibles if estado_de(cv_id)["estado"] != "DISPONIBLE"
            ),
            "candidatos": [
                {**c, "nombre_archivo": disponibles[c["id"]].nombre_archivo,
                 "nombre": leidas[c["id"]].get("nombre_completo"),
                 "localidad": leidas[c["id"]].get("localidad"),
                 "resumen": leidas[c["id"]].get("resumen"),
                 "estado": estado_de(c["id"])}
                for c in candidatos
            ],
        }

    @app.put("/cvs/{cv_id}/estado")
    def marcar_estado(cv_id: str, entrada: EstadoEntrada, sesion: SesionActual):
        """Contratado o «no volver a convocar» con motivo laboral: sale de las búsquedas."""
        if originales.obtener_original(cv_id) is None:
            raise HTTPException(404, "CV inexistente")
        estado = entrada.estado.upper()
        if estado not in ESTADOS_CV:
            raise HTTPException(400, "Estado inexistente.")
        motivo = entrada.motivo.strip()
        if estado == "NO_CONVOCAR" and len(motivo) < 10:
            raise HTTPException(400, "Escribí un motivo laboral concreto (al menos 10 caracteres).")
        if estado != "DISPONIBLE" and not motivo:
            raise HTTPException(400, "Escribí el motivo o el puesto.")
        anterior = estado_de(cv_id)
        nuevo = {"estado": estado, "motivo": motivo, "por": sesion.actor,
                 "en": datetime.now(UTC).isoformat()}
        estados[cv_id] = nuevo
        historial_estados.append({**nuevo, "cv_id": cv_id, "anterior": anterior["estado"]})
        return nuevo

    @app.get("/cvs/{cv_id}/auditoria")
    def auditoria(cv_id: str):
        return extracciones.consultas_original(cv_id)

    return app


def crear_app(perfiles, entorno: str = "prueba", ruta_base: str = "datos/modulos.sqlite3") -> FastAPI:
    app = FastAPI(title="Selección de personal")
    app.include_router(crear_router(perfiles, entorno, ruta_base))
    return app


class CorreoEntrada(BaseModel):
    casilla: str = Field(min_length=3, max_length=200)
    clave_aplicacion: str | None = Field(default=None, max_length=100)


def _paginas(contenido: bytes) -> int | None:
    try:
        import pypdfium2

        documento = pypdfium2.PdfDocument(contenido)
    except Exception:  # noqa: BLE001 - PDF roto o sin renderizador
        return None
    try:
        return len(documento)
    finally:
        documento.close()


def construir_correo(ruta_base: str, clave: str, entorno: str = "produccion") -> CorreoRRHH:
    originales = OriginalesSQLite(ruta_base)
    extracciones = ExtraccionesSQLite(ruta_base)
    return CorreoRRHH(
        correo_rrhh_sqlite(ruta_base),
        CifradorAESGCM(hashlib.scrypt(clave.encode(), salt=b"suite-juviar-parametros", n=2**14, r=8, p=1, dklen=32)),
        lambda casilla, clave_app, ultima, cursor: BandejaGmailIMAP(casilla, clave_app, desde_para(ultima), cursor),
        IngestarCVs(originales),
        ExtraerDatosCV(originales, extracciones, TextoPDF(), CamposPorReglasProvisorias()),
        enviar_por_gmail,
        al_incorporar=_al_incorporar(ruta_base, entorno),
    )


def construir_cvs_whatsapp(ruta_base: str, entorno: str = "produccion") -> IncorporarCVWhatsapp:
    """CV que llegan por WhatsApp (infra/042): mismo guardado y extracción que los del mail."""
    originales = OriginalesSQLite(ruta_base)
    extracciones = ExtraccionesSQLite(ruta_base)
    return IncorporarCVWhatsapp(
        IngestarCVs(originales),
        ExtraerDatosCV(originales, extracciones, TextoPDF(), CamposPorReglasProvisorias()),
        extracciones,
        al_incorporar=_al_incorporar(ruta_base, entorno),
    )


def crear_router_parametros(correo: CorreoRRHH | None, entorno: str = "prueba") -> APIRouter:
    """Parámetros de la casilla de RRHH; sólo administradores."""
    exigir_identidad_configurada(entorno)
    app = APIRouter(dependencies=[Depends(exigir_permiso("parametros.gestionar"))])

    def servicio() -> CorreoRRHH:
        if correo is None:
            raise HTTPException(503, "Falta configurar SJ_CLAVE_PARAMETROS en el servidor.")
        return correo

    @app.get("/correo-rrhh")
    def listar_correos():
        return servicio().listar()

    @app.put("/correo-rrhh/{codigo}")
    def guardar_correo(codigo: str, entrada: CorreoEntrada, sesion: SesionActual):
        try:
            return servicio().guardar(codigo, entrada.casilla, entrada.clave_aplicacion, sesion.actor)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/correo-rrhh/{codigo}/probar")
    def probar_correo(codigo: str):
        try:
            servicio().probar(codigo)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ErrorCorreo as exc:
            raise HTTPException(502, str(exc)) from exc
        return {"ok": True}

    @app.post("/correo-rrhh/{codigo}/leer")
    def leer_correo(codigo: str):
        try:
            return asdict(servicio().leer(codigo))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ErrorCorreo as exc:
            raise HTTPException(502, str(exc)) from exc

    return app
