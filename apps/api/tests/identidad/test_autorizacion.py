from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from starlette.routing import Mount

from suite_juviar.plataforma.identidad.api.dependencias import (
    DUENO_CATALOGO_PERMISOS,
    PERMISOS_POR_PERFIL,
    exigir_identidad_configurada,
    exigir_permiso,
    resolver_sesion,
)


def test_sin_sesion_es_401_y_permiso_insuficiente_es_403():
    app = FastAPI()

    @app.get("/protegido", dependencies=[Depends(exigir_permiso("epp.catalogo.editar"))])
    def protegido():
        return {"ok": True}

    from fastapi.testclient import TestClient

    cliente = TestClient(app)
    assert cliente.get("/protegido").status_code == 401
    assert cliente.get(
        "/protegido", headers={"X-Perfil-Simulado": "RRHH"}
    ).status_code == 403
    assert cliente.get(
        "/protegido", headers={"X-Perfil-Simulado": "HYS"}
    ).status_code == 200


def test_produccion_no_admite_identidad_simulada(monkeypatch):
    monkeypatch.delenv("SJ_IDENTIDAD_REAL", raising=False)
    with pytest.raises(RuntimeError, match="identidad simulada"):
        exigir_identidad_configurada("produccion")


def test_catalogo_tiene_dueno_y_perfiles_agrupan_permisos():
    assert DUENO_CATALOGO_PERMISOS == "RRHH junto con Sistemas"
    assert "epp.catalogo.editar" in PERMISOS_POR_PERFIL["HYS"]
    assert "epp.catalogo.editar" not in PERMISOS_POR_PERFIL["RRHH"]
    assert "seleccion.gestionar" in PERMISOS_POR_PERFIL["RRHH"]


def test_control_negativo_quitar_permiso_produce_403(monkeypatch):
    originales = PERMISOS_POR_PERFIL["HYS"]
    monkeypatch.setitem(
        PERMISOS_POR_PERFIL, "HYS", originales - {"epp.catalogo.editar"}
    )
    sesion = resolver_sesion(
        perfil="HYS", actor="hys", empresa="ENAV", legajo_declarado=None
    )
    dependencia = exigir_permiso("epp.catalogo.editar")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        dependencia(sesion)
    assert error.value.status_code == 403


def permisos_de_ruta(ruta: APIRoute) -> set[str]:
    return {
        permiso
        for dependencia in ruta.dependant.dependencies
        if (permiso := getattr(dependencia.call, "permiso_requerido", None))
    }


def test_toda_ruta_de_un_router_protegido_declara_permiso():
    router = APIRouter(dependencies=[Depends(exigir_permiso("seleccion.gestionar"))])

    @router.get("/uno")
    def uno():
        return None

    @router.post("/dos")
    def dos():
        return None

    rutas = [ruta for ruta in router.routes if isinstance(ruta, APIRoute)]
    assert rutas
    assert all(permisos_de_ruta(ruta) for ruta in rutas)


def test_todas_las_rutas_reales_de_la_api_declaran_permiso(monkeypatch):
    monkeypatch.setenv("SJ_HMAC_DATOS_PERSONALES", "h" * 32)
    monkeypatch.setenv("SJ_CLAVE_CIFRADO_DATOS_PERSONALES", "c" * 32)
    monkeypatch.setenv("SJ_ENTORNO", "prueba")
    from suite_juviar.main import app

    rutas: list[tuple[str, APIRoute]] = []

    def recorrer(aplicacion, prefijo: str = ""):
        for ruta in aplicacion.routes:
            if isinstance(ruta, APIRoute):
                rutas.append((f"{prefijo}{ruta.path}", ruta))
            elif isinstance(ruta, Mount) and hasattr(ruta.app, "routes"):
                recorrer(ruta.app, f"{prefijo}{ruta.path}")

    recorrer(app)
    abiertas = [ruta for ruta, objeto in rutas if not permisos_de_ruta(objeto)]
    assert rutas
    assert abiertas == []
