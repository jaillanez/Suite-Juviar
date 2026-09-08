"""Un solo backend desplegable. Los routers se montan acá y en ningún otro lado."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from suite_juviar.modulos.recepcion.api.router import router as recepcion_router
from suite_juviar.modulos.rrhh_epp.api.mvp import crear_app as crear_rrhh_epp_app
from suite_juviar.modulos.rrhh_epp.mvp import construir as construir_rrhh_epp
from suite_juviar.plataforma.identidad.api import router as identidad_router
from suite_juviar.plataforma.identidad.api.dependencias import (
    exigir_identidad_configurada,
    exigir_permiso,
)

from .composicion.olas_3_4_5 import construir_subaplicaciones

entorno = (__import__("os").getenv("SJ_ENTORNO") or __import__("os").getenv("ENTORNO") or "desarrollo")
exigir_identidad_configurada(entorno)
app = FastAPI(title="Suite Juviar", version="0.1.0")

app.include_router(identidad_router, prefix="/api/v1")
app.include_router(recepcion_router, prefix="/api/v1")
rrhh_epp = construir_rrhh_epp()
app.mount("/api/v1/rrhh-epp", crear_rrhh_epp_app(rrhh_epp))
for nombre, subaplicacion in construir_subaplicaciones(rrhh_epp).items():
    app.mount(f"/api/v1/{nombre}", subaplicacion)
# app.include_router(turnos_router, prefix="/api/v1")
# app.include_router(cosecha_router, prefix="/api/v1")


@app.get("/salud", dependencies=[Depends(exigir_permiso("suite.acceder"))])
async def salud() -> dict[str, str]:
    return {"estado": "ok"}
