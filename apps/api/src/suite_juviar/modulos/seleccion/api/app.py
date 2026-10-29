from __future__ import annotations

import os
from base64 import b64decode, b64encode
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from suite_juviar.plataforma.identidad.api.dependencias import (
    SesionActual,
    exigir_identidad_configurada,
    exigir_permiso,
)

from ..application.extraccion import ExtraerDatosCV
from ..application.ranking import EvaluarBusqueda, ordenar_resultados
from ..domain.modelos import (
    Busqueda,
    ConfirmacionCampo,
    ConsultaOriginal,
    CVOriginal,
    OrigenCV,
    PerfilBusqueda,
)
from ..infrastructure import ia_deepseek
from ..infrastructure.extraccion_pdf import CamposPorReglasProvisorias, TextoPDF
from ..infrastructure.sqlite import (
    ExtraccionesSQLite,
    OriginalesSQLite,
    busquedas_sqlite,
    consultas_ia_sqlite,
    estados_cv_sqlite,
    fichas_ia_sqlite,
    historial_estados_sqlite,
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


ESTADOS_CV = {"DISPONIBLE", "CONTRATADO", "NO_CONVOCAR"}


class EstadoEntrada(BaseModel):
    estado: str
    motivo: str = Field(default="", max_length=500)


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

    def estado_de(cv_id: str) -> dict[str, object]:
        return estados.get(cv_id) or {"estado": "DISPONIBLE"}
    texto_pdf = TextoPDF()
    # Mandar CV a DeepSeek saca datos personales de la empresa: en producción sólo con
    # autorización expresa en la configuración del servidor.
    ia_permitida = entorno.lower() not in {"produccion", "production", "prod"} or (
        os.getenv("SJ_IA_EXTERNA_AUTORIZADA", "").strip().lower() in {"1", "true", "si"}
    )

    def exigir_ia() -> None:
        if not ia_permitida:
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
                "estado": estado_de(original.id),
            })
        if busqueda:
            por_id = {fila["id"]: fila for fila in filas}
            ordenados = ordenar_resultados([fila["resultado"] for fila in filas if fila["resultado"]])
            return [por_id[resultado.id_original] for resultado in ordenados]
        return filas

    @app.get("/revision")
    def revision():
        return [fila for fila in listar_cvs() if fila["requiere_revision"]]

    @app.get("/cvs/{cv_id}")
    def ficha_cv(cv_id: str, busqueda_id: str | None = None):
        original = originales.obtener_original(cv_id)
        extraccion = extracciones.obtener_extraccion(cv_id)
        if original is None or extraccion is None:
            raise HTTPException(404, "CV inexistente")
        busqueda = busquedas.get(busqueda_id) if busqueda_id else None
        return {
            "id": cv_id,
            "nombre": original.nombre_archivo,
            "campos": list(extraccion.campos),
            "pendientes": list(extraccion.campos_pendientes),
            "confirmaciones": extracciones.confirmaciones(cv_id),
            "estado": estado_de(cv_id),
            "historial_estado": [h for h in historial_estados if h["cv_id"] == cv_id],
            "resultado": evaluar.ejecutar(busqueda, extraccion) if busqueda else None,
            "marca": "DATOS SIMULADOS — SIN VALIDEZ",
        }

    @app.put("/cvs/{cv_id}/campos/{campo}/confirmacion")
    def confirmar_campo(
        cv_id: str,
        campo: str,
        entrada: ConfirmacionEntrada,
        sesion: SesionActual,
    ):
        extraccion = extracciones.obtener_extraccion(cv_id)
        if extraccion is None:
            raise HTTPException(404, "CV inexistente")
        extraido = next((valor for valor in extraccion.campos if valor.nombre == campo), None)
        if extraido is None:
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
        total = len(originales.listar_originales())
        leidos = sum(1 for o in originales.listar_originales() if o.id in fichas_ia)
        return {"disponible": ia_permitida and ia_deepseek.disponible(), "total": total, "leidos": leidos}

    @app.get("/ia/fichas")
    def fichas():
        return {cv_id: ficha for cv_id, ficha in fichas_ia.items()}

    @app.post("/cvs/{cv_id}/leer-ia")
    def leer_con_ia(cv_id: str, sesion: SesionActual):
        exigir_ia()
        cv = originales.obtener_original(cv_id)
        if cv is None:
            raise HTTPException(404, "CV inexistente")
        try:
            ficha = ia_deepseek.leer_cv(cv.nombre_archivo, cv.contenido, texto_pdf.extraer_texto(cv.contenido))
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc
        ficha = {**ficha, "leido_por": sesion.actor, "leido_en": datetime.now(UTC).isoformat()}
        fichas_ia[cv_id] = ficha
        return ficha

    @app.post("/ia/buscar")
    def buscar_con_ia(entrada: PedidoEntrada, sesion: SesionActual):
        exigir_ia()
        disponibles = {o.id: o for o in originales.listar_originales()}
        leidas = {
            cv_id: f for cv_id, f in fichas_ia.items()
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
