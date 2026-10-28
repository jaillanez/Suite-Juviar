"""§6.5: los permisos se prueban aplicados, no sólo escritos en SQL."""

from __future__ import annotations

import os

import psycopg
import pytest
from psycopg import errors, sql

pytestmark = pytest.mark.local
DSN_SUITE = os.environ.get(
    "TEST_DSN_SUITE",
    "postgresql://localhost:5432/juviar_suite_local",
)


def _puede_leer(rol: str, esquema: str, tabla: str) -> bool:
    with psycopg.connect(DSN_SUITE, autocommit=True) as cn, cn.cursor() as cur:
        cur.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(rol)))
        try:
            cur.execute(
                sql.SQL("SELECT 1 FROM {}.{} LIMIT 0").format(
                    sql.Identifier(esquema),
                    sql.Identifier(tabla),
                )
            )
        except errors.InsufficientPrivilege:
            return False
        return True


@pytest.mark.parametrize(
    ("rol", "esquema", "tabla"),
    [
        ("suite_rrhh_epp", "rrhh_epp", "entrega_epp"),
        ("suite_seleccion_rrhh", "seleccion", "cv_original"),
        ("suite_capacitacion_rrhh", "capacitacion", "asistencia"),
    ],
)
def test_cada_servicio_puede_leer_su_propio_esquema(rol, esquema, tabla):
    """Control de la sonda: evita un falso verde por una conexión siempre fallida."""
    assert _puede_leer(rol, esquema, tabla) is True


@pytest.mark.parametrize(
    ("rol", "esquema", "tabla"),
    [
        ("suite_rrhh_epp", "seleccion", "cv_original"),
        ("suite_rrhh_epp", "capacitacion", "asistencia"),
        ("suite_seleccion_rrhh", "rrhh_epp", "entrega_epp"),
        ("suite_seleccion_rrhh", "capacitacion", "asistencia"),
        ("suite_capacitacion_rrhh", "rrhh_epp", "entrega_epp"),
        ("suite_capacitacion_rrhh", "seleccion", "cv_original"),
        ("suite_sin_acceso", "rrhh_epp", "entrega_epp"),
        ("suite_sin_acceso", "seleccion", "cv_original"),
        ("suite_sin_acceso", "capacitacion", "asistencia"),
    ],
)
def test_un_rol_ajeno_no_puede_leer_datos_del_modulo(rol, esquema, tabla):
    assert _puede_leer(rol, esquema, tabla) is False
