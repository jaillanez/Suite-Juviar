"""Outbox transaccional y publicación idempotente de contactos hacia la DMZ."""

from __future__ import annotations

import logging

import psycopg
from psycopg.rows import dict_row

log = logging.getLogger(__name__)


def encolar(cn, clientecuit: str, telefono: str) -> None:
    cn.execute(
        """INSERT INTO terceros.contacto_publicacion
           (telefono,clientecuit,activo,tareas)
           SELECT telefono,clientecuit,activo,tareas
           FROM terceros.contacto_whatsapp
           WHERE clientecuit=%s AND telefono=%s
           ON CONFLICT (telefono,clientecuit) DO UPDATE SET
             activo=EXCLUDED.activo,tareas=EXCLUDED.tareas,
             version=terceros.contacto_publicacion.version+1,
             pendiente_desde=now(),publicado_en=NULL,ultimo_error=NULL""",
        (clientecuit, telefono),
    )


class PublicadorContactos:
    def __init__(self, dsn_suite: str, dsn_dmz: str) -> None:
        self.dsn_suite = dsn_suite
        self.dsn_dmz = dsn_dmz

    def publicar(self, limite: int = 100) -> int:
        publicados = 0
        with psycopg.connect(self.dsn_suite, row_factory=dict_row) as suite:
            filas = suite.execute(
                """SELECT * FROM terceros.contacto_publicacion
                   WHERE publicado_en IS NULL
                   ORDER BY pendiente_desde
                   FOR UPDATE SKIP LOCKED LIMIT %s""",
                (limite,),
            ).fetchall()
            for fila in filas:
                try:
                    with psycopg.connect(self.dsn_dmz) as dmz:
                        dmz.execute(
                            """INSERT INTO consulta.telefono_productor
                               (telefono,clientecuit,activo,tareas)
                               VALUES (%s,%s,%s,%s)
                               ON CONFLICT (telefono,clientecuit) DO UPDATE SET
                                 activo=EXCLUDED.activo,tareas=EXCLUDED.tareas""",
                            (
                                fila["telefono"],
                                fila["clientecuit"],
                                fila["activo"],
                                fila["tareas"],
                            ),
                        )
                    suite.execute(
                        """UPDATE terceros.contacto_publicacion
                           SET publicado_en=now(),intentos=intentos+1,ultimo_error=NULL
                           WHERE telefono=%s AND clientecuit=%s AND version=%s""",
                        (fila["telefono"], fila["clientecuit"], fila["version"]),
                    )
                    publicados += 1
                except psycopg.Error as exc:
                    suite.execute(
                        """UPDATE terceros.contacto_publicacion
                           SET intentos=intentos+1,ultimo_error=%s
                           WHERE telefono=%s AND clientecuit=%s""",
                        (str(exc)[:1000], fila["telefono"], fila["clientecuit"]),
                    )
                    log.warning("contacto pendiente de publicar: %s", exc)
        return publicados
