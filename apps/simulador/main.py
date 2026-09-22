"""Simulador interno; sólo acepta conexiones originadas en loopback."""

from __future__ import annotations

import os
import time
from ipaddress import ip_address
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

HTML = (Path(__file__).parent / "chat.html").read_text(encoding="utf-8")


def es_local(host: str | None) -> bool:
    try:
        return host is not None and ip_address(host).is_loopback
    except ValueError:
        return False


def exigir_local(request: Request) -> None:
    if not es_local(request.client.host if request.client else None):
        raise HTTPException(status_code=403)


def payload_meta(telefono: str, texto: str, wamid: str, marca: int) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "simulador",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "simulador",
                                "phone_number_id": "simulador",
                            },
                            "contacts": [
                                {"profile": {"name": "Simulador"}, "wa_id": telefono}
                            ],
                            "messages": [
                                {
                                    "from": telefono,
                                    "id": wamid,
                                    "timestamp": str(marca),
                                    "type": "text",
                                    "text": {"body": texto},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


class Envio(BaseModel):
    telefono: str = Field(pattern=r"^\d{8,20}$")
    texto: str = Field(min_length=1, max_length=1000)


def crear_app(cliente_http: httpx.Client | None = None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, dependencies=[Depends(exigir_local)])
    cliente = cliente_http or httpx.Client(timeout=10)

    def url_webhook() -> str:
        base = os.environ["SIM_WEBHOOK_URL"].rstrip("/")
        return f"{base}/{os.environ['BOT_WEBHOOK_SECRETO']}"

    @app.get("/", response_class=HTMLResponse)
    def inicio() -> str:
        return HTML

    @app.post("/enviar")
    def enviar(envio: Envio) -> dict[str, str]:
        wamid = f"sim.in.{uuid4().hex}"
        respuesta = cliente.post(
            url_webhook(),
            json=payload_meta(envio.telefono, envio.texto, wamid, int(time.time())),
        )
        if respuesta.status_code != 200:
            raise HTTPException(
                status_code=502, detail=f"webhook respondió {respuesta.status_code}"
            )
        return {"wamid": wamid}

    @app.get("/respuestas")
    def respuestas(
        telefono: str = Query(pattern=r"^\d{8,20}$"), desde_id: int = Query(0, ge=0)
    ) -> list[dict]:
        with psycopg.connect(os.environ["SIM_DSN"], row_factory=dict_row) as conexion:
            return conexion.execute(
                """SELECT id, texto, creado_en FROM consulta.bot_salida_simulada
                   WHERE telefono = %s AND id > %s ORDER BY id LIMIT 50""",
                (telefono, desde_id),
            ).fetchall()

    @app.get("/telefonos")
    def telefonos() -> list[dict]:
        with psycopg.connect(os.environ["SIM_DSN"], row_factory=dict_row) as conexion:
            return conexion.execute(
                """SELECT telefono, string_agg(nroinscripto, ', ') AS inscriptos
                   FROM consulta.telefono_productor WHERE activo
                   GROUP BY telefono ORDER BY telefono LIMIT 200"""
            ).fetchall()

    return app


app = crear_app()
