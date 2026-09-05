"""Fixtures del entorno de verificación local.

Estas pruebas NO corren en la suite normal de tests: necesitan las dos
bases del PostgreSQL local. Se ejecutan con el marcador -m local.
"""
from __future__ import annotations

import os
import pathlib

import psycopg
import pytest

DSN_ADMIN_DMZ = os.environ.get(
    "TEST_DSN_ADMIN_DMZ", "postgresql://localhost:5432/juviar_web_local"
)
DSN_SITIO = os.environ.get(
    "TEST_DSN_SITIO",
    "postgresql://web_sitio:sitio_local@localhost:5432/juviar_web_local",
)
DSN_WORKER = os.environ.get(
    "TEST_DSN_WORKER",
    "postgresql://web_worker:worker_local@localhost:5432/juviar_web_local",
)
DSN_SUITE = os.environ.get(
    "TEST_DSN_SUITE", "postgresql://localhost:5432/juviar_suite_local"
)

RAIZ = pathlib.Path(__file__).resolve().parents[2]


def _ejecutar_sql(dsn: str, ruta: pathlib.Path) -> None:
    with psycopg.connect(dsn, autocommit=True) as cn, cn.cursor() as cur:
        cur.execute(ruta.read_text(encoding="utf-8"))


@pytest.fixture(scope="session", autouse=True)
def esquemas() -> None:
    """Aplica las migraciones una vez por corrida."""
    _ejecutar_sql(DSN_ADMIN_DMZ, RAIZ / "apps/web/sql/001_bandeja_web.sql")
    _ejecutar_sql(DSN_ADMIN_DMZ, RAIZ / "infra/002_roles_local.sql")
    _ejecutar_sql(DSN_ADMIN_DMZ, RAIZ / "infra/004_catalogos_local.sql")
    _ejecutar_sql(DSN_SUITE, RAIZ / "infra/003_suite_minima.sql")


@pytest.fixture()
def bandeja_limpia() -> None:
    with psycopg.connect(DSN_ADMIN_DMZ, autocommit=True) as cn, cn.cursor() as cur:
        cur.execute("TRUNCATE web.bandeja_solicitudes;")
    with psycopg.connect(DSN_SUITE, autocommit=True) as cn, cn.cursor() as cur:
        cur.execute("TRUNCATE comercial.solicitud_muestra;")
