"""Un solo backend desplegable. Los routers se montan acá y en ningún otro lado."""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI

from suite_juviar.modulos.recepcion.api.router import router as recepcion_router
from suite_juviar.modulos.rrhh_epp.api.mvp import crear_app as crear_rrhh_epp_app
from suite_juviar.modulos.rrhh_epp.mvp import construir as construir_rrhh_epp
from suite_juviar.plataforma.identidad.api import router as identidad_router
from suite_juviar.plataforma.identidad.api.dependencias import (
    exigir_identidad_configurada,
    exigir_permiso,
)
from suite_juviar.plataforma.terceros.api.contactos import configurar as configurar_contactos
from suite_juviar.plataforma.terceros.api.contactos import router as contactos_router
from suite_juviar.plataforma.terceros.application.contactos import GestionarContactos
from suite_juviar.plataforma.terceros.infrastructure.contactos_postgres import (
    ContactosPostgreSQL,
)

from .composicion.olas_3_4_5 import construir_subaplicaciones

entorno = os.getenv("SJ_ENTORNO") or os.getenv("ENTORNO") or "desarrollo"
exigir_identidad_configurada(entorno)
app = FastAPI(title="Suite Juviar", version="0.1.0")

app.include_router(identidad_router, prefix="/api/v1")
app.include_router(recepcion_router, prefix="/api/v1")
dsn_contactos = os.getenv("SJ_CONTACTOS_DSN", os.getenv("RECEPCION_DSN_SUITE", "")).strip()
if dsn_contactos:
    configurar_contactos(
        GestionarContactos(
            ContactosPostgreSQL(dsn_contactos, os.getenv("RECEPCION_DSN_DMZ", "").strip())
        )
    )
app.include_router(contactos_router, prefix="/api/v1")
rrhh_epp = construir_rrhh_epp()
app.mount("/api/v1/rrhh-epp", crear_rrhh_epp_app(rrhh_epp))
for nombre, subaplicacion in construir_subaplicaciones(rrhh_epp).items():
    app.mount(f"/api/v1/{nombre}", subaplicacion)
# app.include_router(turnos_router, prefix="/api/v1")
# app.include_router(cosecha_router, prefix="/api/v1")


@app.get("/salud", dependencies=[Depends(exigir_permiso("suite.acceder"))])
async def salud() -> dict[str, str]:
    return {"estado": "ok"}
