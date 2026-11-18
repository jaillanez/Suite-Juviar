"""Remitos que ve la guardia y mensajes de WhatsApp de mantenimiento, en la base de la fila (infra/041).

Gestión no escribe las tablas: usa funciones de la base que validan y dejan quién hizo cada cosa.
"""

from __future__ import annotations

import json

import psycopg
from psycopg.rows import dict_row

from ..domain.puertos import MensajeEntrante, Salida
from ..domain.remitos import Remito


class PuertaSinConfigurar:
    """Sin conexión a la base de la fila (pruebas o servidor sin configurar)."""

    def publicar(self, remito: Remito) -> None:
        raise RuntimeError("Falta configurar la conexión con la guardia.")

    def anular(self, remito_id: str, actor: str) -> None:
        raise RuntimeError("Falta configurar la conexión con la guardia.")

    def salidas(self, remito_ids: list[str]) -> dict[str, Salida]:
        return {}

    def tomar_mensajes(self) -> list[MensajeEntrante]:
        return []

    def confirmar_mensajes(self, ids: list[str]) -> None:
        return None


class PuertaDMZ:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _conectar(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, connect_timeout=5, row_factory=dict_row)

    def publicar(self, remito: Remito) -> None:
        assert remito.firma is not None
        items = [{"descripcion": i.descripcion, "codigo": i.codigo, "cantidad": i.cantidad} for i in remito.items]
        try:
            with self._conectar() as cn:
                cn.execute("SELECT fila.publicar_remito(%s, %s::integer, %s, %s, %s, %s::jsonb, %s, %s)",
                           (remito.id, remito.numero, remito.bodega, remito.destino, remito.motivo,
                            json.dumps(items), remito.firma.modo.value, remito.firma.por))
        except psycopg.errors.RaiseException as exc:
            raise ValueError(exc.diag.message_primary or "la base rechazó el remito") from exc

    def anular(self, remito_id: str, actor: str) -> None:
        try:
            with self._conectar() as cn:
                cn.execute("SELECT fila.anular_remito(%s, %s)", (remito_id, actor))
        except psycopg.errors.RaiseException as exc:
            raise ValueError(exc.diag.message_primary or "la base rechazó la anulación") from exc

    def salidas(self, remito_ids: list[str]) -> dict[str, Salida]:
        with self._conectar() as cn:
            filas = cn.execute("SELECT * FROM fila.salidas_remitos(%s::text[])", (remito_ids,)).fetchall()
        return {f["id"]: Salida(f["salio_en"], f["salio_por"]) for f in filas}

    def tomar_mensajes(self) -> list[MensajeEntrante]:
        with self._conectar() as cn:
            filas = cn.execute("SELECT * FROM fila.mensajes_mantenimiento_pendientes(50)").fetchall()
        return [MensajeEntrante(str(f["id"]), f["telefono"], f["nombre"], f["texto"] or "", f["recibido_en"],
                                bytes(f["foto"]) if f["foto"] is not None else None, f["foto_tipo"] or "")
                for f in filas]

    def confirmar_mensajes(self, ids: list[str]) -> None:
        with self._conectar() as cn:
            cn.execute("SELECT fila.confirmar_mensajes_mantenimiento(%s::bigint[])", ([int(i) for i in ids],))
