"""Verificación 3 — el límite por hora distingue visitantes de verdad.

apps/web limita por request.client.host. Detrás de nginx, sin
--proxy-headers en uvicorn, TODAS las solicitudes llegan con la IP del
proxy: el límite se agota con un solo visitante y bloquea a los demás.
Con --proxy-headers, uvicorn reemplaza client.host por X-Forwarded-For.

Estas pruebas corren contra un uvicorn levantado por el script
infra/verificar.sh, que lo arranca de las dos maneras.
"""
from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.local

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8080")
LIMITE = int(os.environ.get("WEB_LIMITE_HORA", "30"))


def _solicitud_valida() -> dict:
    return {
        "client_metadata": {
            "company_name": "Global Ingredients Ltd",
            "contact_email": "compras@example.com",
            "country": "US",
            "industry_segment": "Beverage_Manufacturing",
        },
        "product_line": "bulk_wine",
        "projected_volume": {"annual_tons": 800, "shipment_format": "Flexitank_4650_gal"},
        "lab_specs": {"target_brix": 68.0, "ph_target": 3.45},
        "certifications_required": ["FSSC_22000"],
    }


def _cliente_con_token() -> tuple[httpx.Client, dict]:
    cliente = httpx.Client(base_url=BASE, timeout=10)
    portada = cliente.get("/")
    token = portada.cookies.get("csrf") or cliente.cookies.get("csrf")
    return cliente, {"X-CSRF-Token": token or ""}


def test_sin_token_csrf_rechaza() -> None:
    cliente = httpx.Client(base_url=BASE, timeout=10)
    r = cliente.post("/api/muestras", json=_solicitud_valida())
    assert r.status_code == 403


def test_ip_distinta_no_consume_el_cupo_ajena() -> None:
    """Requiere uvicorn con --proxy-headers. Sin él, ambas IPs se ven igual
    y la segunda tanda recibe 429: eso es exactamente la falla que se busca."""
    cliente, cabeceras = _cliente_con_token()

    for i in range(LIMITE + 2):
        r = cliente.post(
            "/api/muestras",
            json=_solicitud_valida(),
            headers={**cabeceras, "X-Forwarded-For": "198.51.100.10"},
        )
        if r.status_code == 429:
            break
    else:
        pytest.fail("nunca se alcanzó el límite: el rate limit no está activo")

    r = cliente.post(
        "/api/muestras",
        json=_solicitud_valida(),
        headers={**cabeceras, "X-Forwarded-For": "198.51.100.99"},
    )
    assert r.status_code != 429, (
        "una IP distinta quedó bloqueada por el cupo de otra: "
        "falta --proxy-headers en el arranque de uvicorn"
    )


def test_linea_de_producto_inventada_se_rechaza() -> None:
    cliente, cabeceras = _cliente_con_token()
    cuerpo = _solicitud_valida()
    cuerpo["product_line"] = "vino_de_marte"
    r = cliente.post("/api/muestras", json=cuerpo, headers=cabeceras)
    assert r.status_code == 422
