"""Pruebas de integración en una base vacía indicada por FILA_TEST_DSN_ADMIN."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fila_app.repositorio import RepositorioFila

DSN = os.environ.get("FILA_TEST_DSN_ADMIN")
pytestmark = pytest.mark.skipif(not DSN, reason="sin FILA_TEST_DSN_ADMIN")
RAIZ = Path(__file__).resolve().parents[2]
SJ = timezone(timedelta(hours=-3))


def _dsn_rol(rol: str) -> str:
    datos = psycopg.conninfo.conninfo_to_dict(DSN)
    datos.update(user=rol, password="x")
    return psycopg.conninfo.make_conninfo(**datos)


@pytest.fixture(scope="module", autouse=True)
def esquema():
    with psycopg.connect(DSN, autocommit=True) as cn:
        cn.execute("DROP SCHEMA IF EXISTS fila CASCADE; DROP SCHEMA IF EXISTS consulta CASCADE")
        cn.execute(
            """CREATE SCHEMA consulta;
               CREATE TABLE consulta.descarga_publica(
                 sede text, ciu text, fecha timestamp, clientecuit text,
                 estado text, PRIMARY KEY(sede,ciu))"""
        )
        cn.execute((RAIZ / "infra/020_fila_camiones.sql").read_text())
        cn.execute((RAIZ / "infra/022_correcciones_fila.sql").read_text())
        for rol in ("fila_guardia", "fila_worker"):
            cn.execute(f"ALTER ROLE {rol} PASSWORD 'x'")


@pytest.fixture()
def limpio():
    with psycopg.connect(DSN, autocommit=True) as cn:
        cn.execute(
            "TRUNCATE fila.evento, fila.viaje, fila.turno, consulta.descarga_publica CASCADE"
        )


def _pendiente(patente="AB123CD"):
    with psycopg.connect(DSN, autocommit=True) as cn:
        return cn.execute(
            """INSERT INTO fila.viaje
               (id_cliente,ticket,productor_texto,sede,patente,origen,estado)
               VALUES (%s,%s,'x','chimbas',%s,'qr','pendiente') RETURNING id""",
            (uuid4(), uuid4().hex + uuid4().hex, patente),
        ).fetchone()[0]


def _alta(repo, patente="AB123CD", momento=None):
    return repo.alta_directa(
        {
            "id_cliente": uuid4(),
            "sede": "chimbas",
            "patente": patente,
            "productor": "P",
            "telefono": None,
            "clientecuit": "20-11111111-1",
            "clientecodigo": None,
            "declara_organica": False,
            "momento_cliente": momento or datetime.now(UTC),
        },
        "guardia:tablet",
    )


def test_worker_puede_leer_pero_no_modificar_descargas():
    with psycopg.connect(_dsn_rol("fila_worker")) as cn:
        cn.execute("SELECT id_suite, fecha FROM consulta.descarga_publica LIMIT 1")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cn.execute("DELETE FROM consulta.descarga_publica")


def test_registro_del_qr_no_traba_al_guardia(limpio):
    pendiente = _pendiente()
    viaje = _alta(RepositorioFila(_dsn_rol("fila_guardia")))
    assert viaje["estado"] == "en_espera"
    with psycopg.connect(DSN) as cn:
        estado, motivo = cn.execute(
            "SELECT estado,motivo_cierre FROM fila.viaje WHERE id=%s", (pendiente,)
        ).fetchone()
    assert (estado, motivo) == ("cancelado", "reemplazado_por_guardia")


def test_numero_y_dia_de_un_camion_nocturno(limpio, monkeypatch):
    from fila_app import repositorio

    momento = datetime(2026, 3, 3, 22, 30, tzinfo=SJ)
    monkeypatch.setattr(
        repositorio, "_ahora", lambda: momento.astimezone(UTC) + timedelta(minutes=1)
    )
    viaje = _alta(
        RepositorioFila(_dsn_rol("fila_guardia")), momento=momento.astimezone(UTC)
    )
    assert str(viaje["fecha_operativa"]) == "2026-03-03"
