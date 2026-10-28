"""Un solo backend desplegable. Los routers se montan acá y en ningún otro lado."""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI

from suite_juviar.modulos.epp_analitica.api.app import tabla_de_errores as errores_analitica
from suite_juviar.modulos.legajo.api.app import tabla_de_errores as errores_legajo
from suite_juviar.modulos.recepcion.api.router import router as recepcion_router
from suite_juviar.modulos.rrhh_epp.api.mvp import crear_router as crear_rrhh_epp_router
from suite_juviar.modulos.rrhh_epp.api.mvp import tabla_de_errores as errores_rrhh_epp
from suite_juviar.modulos.rrhh_epp.mvp import construir as construir_rrhh_epp
from suite_juviar.modulos.salud.api.app import tabla_de_errores as errores_salud
from suite_juviar.modulos.turnos.api.app import tabla_de_errores as errores_turnos
from suite_juviar.plataforma.db.dsn import dsn_psycopg
from suite_juviar.plataforma.errores import registrar_manejadores
from suite_juviar.plataforma.identidad.api import router as identidad_router
from suite_juviar.plataforma.identidad.api.dependencias import (
    exigir_identidad_configurada,
    exigir_permiso,
)
from suite_juviar.plataforma.terceros.api.contactos import configurar as configurar_contactos
from suite_juviar.plataforma.terceros.api.contactos import router as contactos_router
from suite_juviar.plataforma.terceros.api.guardias import configurar as configurar_guardias
from suite_juviar.plataforma.terceros.api.guardias import router as guardias_router
from suite_juviar.plataforma.terceros.application.contactos import GestionarContactos
from suite_juviar.plataforma.terceros.infrastructure.contactos_postgres import (
    ContactosPostgreSQL,
)

from .composicion.olas_3_4_5 import construir_routers

entorno = os.getenv("SJ_ENTORNO") or os.getenv("ENTORNO") or "desarrollo"
exigir_identidad_configurada(entorno)
app = FastAPI(title="Suite Juviar", version="0.1.0")
registrar_manejadores(
    app,
    [*errores_rrhh_epp(), *errores_legajo(), *errores_salud(),
     *errores_turnos(), *errores_analitica()],
)

app.include_router(identidad_router, prefix="/api/v1")
app.include_router(recepcion_router, prefix="/api/v1")
dsn_contactos = dsn_psycopg(obligatorio=False)
if dsn_contactos:
    configurar_contactos(
        GestionarContactos(
            ContactosPostgreSQL(dsn_contactos, os.getenv("RECEPCION_DSN_DMZ", "").strip())
        )
    )
dsn_dmz = os.getenv("RECEPCION_DSN_DMZ", "").strip()
if dsn_dmz:
    configurar_guardias(dsn_dmz)
app.include_router(contactos_router, prefix="/api/v1")
app.include_router(guardias_router, prefix="/api/v1")
rrhh_epp = construir_rrhh_epp()
app.include_router(crear_rrhh_epp_router(rrhh_epp), prefix="/api/v1/rrhh-epp")
for nombre, router in construir_routers(rrhh_epp).items():
    app.include_router(router, prefix=f"/api/v1/{nombre}")
# app.include_router(turnos_router, prefix="/api/v1")
# app.include_router(cosecha_router, prefix="/api/v1")


@app.get("/salud", dependencies=[Depends(exigir_permiso("suite.acceder"))])
async def salud() -> dict[str, str]:
    return {"estado": "ok"}
