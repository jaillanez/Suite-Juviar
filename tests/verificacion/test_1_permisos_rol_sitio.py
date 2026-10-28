"""Verificación 1 — el sitio público no puede leer lo que escribe.

Es la protección más importante del diseño: si el rol del sitio pudiera
hacer SELECT sobre la bandeja, un visitante que llegue a la conexión vería
las solicitudes de otros clientes. Está escrito en el GRANT, pero un GRANT
escrito no es un permiso verificado.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import psycopg
import pytest
from psycopg import errors

from tests.verificacion.conftest import DSN_SITIO

pytestmark = pytest.mark.local


def test_el_sitio_puede_insertar_una_solicitud(bandeja_limpia) -> None:
    with psycopg.connect(DSN_SITIO) as cn, cn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO web.bandeja_solicitudes
                (referencia, recibido_en, ip_origen, user_agent, idioma, carga)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            ("B2B-TEST-00001", datetime.now(timezone.utc), "203.0.113.7",
             "pytest", "es", json.dumps({"prueba": True})),
        )
        cn.commit()


def test_el_sitio_NO_puede_leer_la_bandeja(bandeja_limpia) -> None:
    with (
        psycopg.connect(DSN_SITIO) as cn,
        cn.cursor() as cur,
        pytest.raises(errors.InsufficientPrivilege),
    ):
        cur.execute("SELECT * FROM web.bandeja_solicitudes;")


def test_el_sitio_NO_puede_borrar_ni_modificar(bandeja_limpia) -> None:
    with (
        psycopg.connect(DSN_SITIO) as cn,
        cn.cursor() as cur,
        pytest.raises(errors.InsufficientPrivilege),
    ):
        cur.execute("DELETE FROM web.bandeja_solicitudes;")
    with (
        psycopg.connect(DSN_SITIO) as cn,
        cn.cursor() as cur,
        pytest.raises(errors.InsufficientPrivilege),
    ):
        cur.execute("UPDATE web.bandeja_solicitudes SET estado = 'procesada';")


def test_el_sitio_SI_puede_leer_los_catalogos() -> None:
    with psycopg.connect(DSN_SITIO) as cn, cn.cursor() as cur:
        cur.execute("SELECT count(*) FROM web.catalogo;")
        assert cur.fetchone() is not None


def test_el_sitio_no_puede_crear_tablas_propias() -> None:
    """PostgreSQL concede el esquema public a todo rol nuevo. Si esta prueba
    falla, falta el REVOKE de 002_roles_local.sql en producción."""
    with (
        psycopg.connect(DSN_SITIO) as cn,
        cn.cursor() as cur,
        pytest.raises(errors.InsufficientPrivilege),
    ):
        cur.execute("CREATE TABLE public.colado (x int);")
