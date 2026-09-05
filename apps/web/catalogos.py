"""Catálogos que alimentan el formulario.

Copia de sólo lectura, materializada en la DMZ. El maestro vive en
`plataforma/parametria` del lado interno y se replica por el mismo worker
que levanta las solicitudes. apps/web NUNCA lee la base interna.
"""
from __future__ import annotations

from dataclasses import dataclass

import psycopg
from psycopg.rows import class_row


@dataclass(frozen=True)
class ItemCatalogo:
    codigo: str
    nombre_es: str
    nombre_en: str


_SELECT = """
SELECT codigo, nombre_es, nombre_en
FROM web.catalogo
WHERE tipo = %(tipo)s AND vigente
ORDER BY orden;
"""


class RepositorioCatalogos:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _leer(self, tipo: str) -> list[ItemCatalogo]:
        with (
            psycopg.connect(self._dsn, row_factory=class_row(ItemCatalogo)) as cn,
            cn.cursor() as cur,
        ):
            cur.execute(_SELECT, {"tipo": tipo})
            return cur.fetchall()

    def lineas_producto(self) -> list[ItemCatalogo]:
        return self._leer("linea_producto")

    def formatos_despacho(self) -> list[ItemCatalogo]:
        return self._leer("formato_despacho")

    def certificaciones(self) -> list[ItemCatalogo]:
        return self._leer("certificacion")

    def codigos_validos(self, tipo: str) -> set[str]:
        return {i.codigo for i in self._leer(tipo)}
