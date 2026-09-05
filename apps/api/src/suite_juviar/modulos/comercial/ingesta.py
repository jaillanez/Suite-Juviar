"""Worker interno: levanta solicitudes de la DMZ y las carga en la suite.

Corre del lado de adentro. La conexión va SIEMPRE de adentro hacia afuera:
la DMZ no inicia nada hacia la red interna. Es la contraparte de entrada
del outbox que ya existe en plataforma/outbox.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime

import psycopg
from psycopg.rows import dict_row

from suite_juviar.plataforma.terceros.application.servicios import ServicioTerceros
from suite_juviar.plataforma.terceros.domain.entidades import TipoTercero

log = logging.getLogger("modulos.comercial.ingesta")

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
RETURNING id, referencia, carga, idioma, recibido_en;
"""

_CERRAR = """
UPDATE web.bandeja_solicitudes
SET estado = %(estado)s, procesada_en = now(), error = %(error)s
WHERE id = %(id)s;
"""


class IngestaSolicitudes:
    def __init__(
        self,
        dsn_dmz: str,
        dsn_suite: str,
        servicio_terceros: ServicioTerceros,
        registrar_bitacora: Callable[..., None],
    ) -> None:
        self._dsn_dmz = dsn_dmz
        self._dsn_suite = dsn_suite
        self._terceros = servicio_terceros
        self._registrar_bitacora = registrar_bitacora

    def ejecutar(self, lote: int = 25) -> int:
        procesadas = 0
        with psycopg.connect(self._dsn_dmz, row_factory=dict_row) as dmz:
            with dmz.cursor() as cur:
                cur.execute(_TOMAR, {"lote": lote})
                filas = cur.fetchall()
                dmz.commit()

            for fila in filas:
                try:
                    self._procesar(fila)
                    estado, error = "procesada", None
                    procesadas += 1
                except Exception as exc:
                    log.exception("solicitud %s falló", fila["referencia"])
                    estado, error = "pendiente", str(exc)[:500]

                with dmz.cursor() as cur:
                    cur.execute(_CERRAR, {"id": fila["id"], "estado": estado, "error": error})
                    dmz.commit()
        return procesadas

    def _procesar(self, fila: dict) -> None:
        carga = fila["carga"] if isinstance(fila["carga"], dict) else json.loads(fila["carga"])
        meta = carga["client_metadata"]

        # Regla 1 de §6.1: no se inventan personas. El comprador entra al
        # registro de terceros, con identificación fiscal extranjera.
        tercero_id = self._terceros.obtener_o_crear(
            tipo=TipoTercero.COMPRADOR_EXTERIOR,
            razon_social=meta["company_name"],
            pais=meta["country"],
            email=meta["contact_email"],
            identificacion_fiscal=None,  # se completa al calificar el lead
        )

        with psycopg.connect(self._dsn_suite) as suite, suite.cursor() as cur:
            cur.execute(
                """
                INSERT INTO comercial.solicitud_muestra
                    (referencia, tercero_id, linea_producto, volumen_anual_t,
                     formato_despacho, especificacion, certificaciones,
                     idioma, recibido_en, planta_asignada, sitio_asignado)
                VALUES
                    (%(ref)s, %(tercero)s, %(linea)s, %(vol)s,
                     %(fmt)s, %(spec)s, %(certs)s,
                     %(idioma)s, %(recibido)s, %(planta)s, %(sitio)s)
                ON CONFLICT (referencia) DO NOTHING;
                """,
                {
                    "ref": fila["referencia"],
                    "tercero": tercero_id,
                    "linea": carga["product_line"],
                    "vol": carga["projected_volume"].get("annual_tons"),
                    "fmt": carga["projected_volume"]["shipment_format"],
                    "spec": json.dumps(carga["lab_specs"]),
                    "certs": carga["certifications_required"],
                    "idioma": fila["idioma"],
                    "recibido": fila["recibido_en"],
                    **self._enrutar(carga),
                },
            )
            suite.commit()

        self._registrar_bitacora(
            evento="comercial.solicitud_muestra.creada",
            entidad=fila["referencia"],
            actor="sistema:ingesta_web",
            momento=datetime.now(UTC),
        )

    @staticmethod
    def _enrutar(carga: dict) -> dict:
        """Enrutamiento autoritativo. El del navegador es sólo informativo."""
        linea = carga["product_line"]
        certs = set(carga["certifications_required"])

        if linea == "bulk_wine":
            return {"planta": "JUVIAR", "sitio": "Lavalle"}
        if linea in {"jcu_decolourised", "jcu_alcoholised"}:
            return {"planta": "JUVIAR", "sitio": "Planta concentradora Lavalle"}
        if certs & {"Organic_Letis", "Kosher"}:
            return {"planta": "ENAV", "sitio": "Chimbas"}
        if linea == "jcu_virgin":
            return {"planta": None, "sitio": None}  # decide Comercial según stock
        return {"planta": "ENAV", "sitio": "Media Agua"}
