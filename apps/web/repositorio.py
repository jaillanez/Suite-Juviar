"""Escritura en la bandeja de entrada de la DMZ.

apps/web no conoce el modelo de datos de la suite. Deja un sobre JSON en
`web.bandeja_solicitudes` y termina ahí. El worker interno lo levanta.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

import psycopg
from psycopg.rows import dict_row

from apps.web.esquemas import SolicitudMuestra

_INSERT = """
INSERT INTO web.bandeja_solicitudes
    (referencia, recibido_en, ip_origen, user_agent, idioma, carga)
VALUES
    (%(referencia)s, %(recibido_en)s, %(ip)s, %(ua)s, %(idioma)s, %(carga)s)
;
"""

_SECUENCIA = "SELECT nextval('web.seq_referencia_solicitud');"


class RepositorioBandeja:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _conexion(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, row_factory=dict_row)

    def proxima_referencia(self) -> str:
        with self._conexion() as cn, cn.cursor() as cur:
            cur.execute(_SECUENCIA)
            n = cur.fetchone()["nextval"]
        return f"B2B-{datetime.now(UTC):%Y}-{n:05d}"

    def guardar(
        self,
        solicitud: SolicitudMuestra,
        referencia: str,
        ip: str | None,
        user_agent: str | None,
        idioma: str,
    ) -> str:
        with self._conexion() as cn, cn.cursor() as cur:
            cur.execute(
                _INSERT,
                {
                    "referencia": referencia,
                    "recibido_en": datetime.now(UTC),
                    "ip": ip,
                    "ua": (user_agent or "")[:400],
                    "idioma": idioma,
                    "carga": json.dumps(solicitud.model_dump(mode="json")),
                },
            )
            cn.commit()
        return referencia
