"""Un solo backend desplegable. Los routers se montan acá y en ningún otro lado."""

from __future__ import annotations

from fastapi import FastAPI

from suite_juviar.modulos.recepcion.api.router import router as recepcion_router

app = FastAPI(title="Suite Juviar", version="0.1.0")

app.include_router(recepcion_router, prefix="/api/v1")
# app.include_router(turnos_router, prefix="/api/v1")
# app.include_router(rrhh_epp_router, prefix="/api/v1")
# app.include_router(cosecha_router, prefix="/api/v1")


@app.get("/salud")
async def salud() -> dict[str, str]:
    return {"estado": "ok"}
