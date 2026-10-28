"""Verificación 2 — dos workers no toman la misma solicitud.

Si el worker corre dos veces a la vez (cron que se solapa, dos servidores,
un reinicio mal hecho), dos procesos podrían levantar la misma fila y
cargar el lead duplicado en la suite. El FOR UPDATE SKIP LOCKED lo evita,
pero sólo se comprueba con dos conexiones simultáneas.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

import psycopg
import pytest

from tests.verificacion.conftest import DSN_ADMIN_DMZ, DSN_SUITE, DSN_WORKER

pytestmark = pytest.mark.local

_TOMAR = """
UPDATE web.bandeja_solicitudes
SET estado = 'tomada', tomada_en = now()
WHERE id IN (
    SELECT id FROM web.bandeja_solicitudes
    WHERE estado = 'pendiente'
    ORDER BY recibido_en
    FOR UPDATE SKIP LOCKED
    LIMIT %(lote)s
)
RETURNING referencia;
"""


def _sembrar(cantidad: int) -> None:
    with psycopg.connect(DSN_ADMIN_DMZ, autocommit=True) as cn, cn.cursor() as cur:
        for i in range(cantidad):
            cur.execute(
                """
                INSERT INTO web.bandeja_solicitudes
                    (referencia, recibido_en, idioma, carga)
                VALUES (%s, %s, 'es', %s)
                """,
                (f"B2B-CONC-{i:05d}", datetime.now(timezone.utc),
                 json.dumps({"product_line": "bulk_wine"})),
            )


def test_dos_workers_se_reparten_las_solicitudes_sin_pisarse(bandeja_limpia) -> None:
    _sembrar(40)
    tomadas: list[list[str]] = [[], []]
    listos = threading.Barrier(2)

    def worker(indice: int) -> None:
        with psycopg.connect(DSN_WORKER) as cn, cn.cursor() as cur:
            listos.wait()  # arrancan al mismo tiempo, no una después de otra
            cur.execute(_TOMAR, {"lote": 25})
            tomadas[indice] = [f[0] for f in cur.fetchall()]
            cn.commit()

    hilos = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    a, b = set(tomadas[0]), set(tomadas[1])

    assert not (a & b), f"ambos workers tomaron las mismas: {sorted(a & b)}"
    assert len(a | b) == 40, "quedaron solicitudes sin tomar"


def test_la_solicitud_no_se_duplica_en_la_suite(bandeja_limpia) -> None:
    """La ingesta usa ON CONFLICT DO NOTHING sobre referencia. Aun si algo
    fallara arriba, la referencia es única y no puede entrar dos veces."""
    _sembrar(1)
    fila = {
        "ref": "B2B-CONC-00000",
        "linea": "bulk_wine",
        "fmt": "Flexitank_4650_gal",
        "spec": json.dumps({"target_brix": 68.0}),
        "recibido": datetime.now(timezone.utc),
    }
    sql = """
        INSERT INTO comercial.solicitud_muestra
            (referencia, linea_producto, formato_despacho, especificacion, recibido_en)
        VALUES (%(ref)s, %(linea)s, %(fmt)s, %(spec)s, %(recibido)s)
        ON CONFLICT (referencia) DO NOTHING;
    """
    with psycopg.connect(DSN_SUITE, autocommit=True) as cn, cn.cursor() as cur:
        cur.execute(sql, fila)
        cur.execute(sql, fila)
        cur.execute(
            "SELECT count(*) FROM comercial.solicitud_muestra WHERE referencia = %s;",
            (fila["ref"],),
        )
        assert cur.fetchone()[0] == 1
