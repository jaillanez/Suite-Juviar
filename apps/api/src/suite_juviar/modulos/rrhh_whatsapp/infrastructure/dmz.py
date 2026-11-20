"""Mensajes para RRHH, CV y recorridos del micro en la base de la fila (infra/042).

Gestión no escribe las tablas: usa funciones de la base que validan y dejan quién hizo cada cosa.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from ..domain.modelos import Confirmacion, CVEntrante, MensajeEntrante


class PuertaSinConfigurar:
    """Sin conexión a la base de la fila (pruebas o servidor sin configurar)."""

    def tomar_mensajes(self) -> list[MensajeEntrante]:
        return []

    def confirmar_mensajes(self, ids: list[str]) -> None:
        return None

    def avisar_lectura(self, mensaje_id: str, texto: str, pide_confirmacion: bool) -> None:
        raise RuntimeError("Falta configurar la conexión con la base de la fila.")

    def confirmaciones(self, ids: list[str]) -> dict[str, Confirmacion]:
        return {}

    def tomar_cvs(self) -> list[CVEntrante]:
        return []

    def confirmar_cvs(self, ids: list[str]) -> None:
        return None

    def recorridos(self) -> list[dict[str, Any]]:
        raise RuntimeError("Falta configurar la conexión con la base de la fila.")

    def guardar_recorrido(self, recorrido_id, sede, nombre, activo, actor) -> dict[str, Any]:
        raise RuntimeError("Falta configurar la conexión con la base de la fila.")

    def personal(self) -> list[dict[str, Any]]:
        raise RuntimeError("Falta configurar la conexión con la base de la fila.")

    def asignar_recorrido(self, telefono, recorrido_id, actor) -> dict[str, Any]:
        raise RuntimeError("Falta configurar la conexión con la base de la fila.")


class PuertaDMZ:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _conectar(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, connect_timeout=5, row_factory=dict_row)

    def tomar_mensajes(self) -> list[MensajeEntrante]:
        with self._conectar() as cn:
            filas = cn.execute("SELECT * FROM fila.mensajes_rrhh_pendientes(20)").fetchall()
        return [MensajeEntrante(str(f["id"]), f["telefono"], f["legajo"], f["nombre"], f["empresa"], f["tipo"],
                                f["texto"] or "", f["recibido_en"],
                                bytes(f["archivo"]) if f["archivo"] is not None else None,
                                f["archivo_tipo"] or "", f["archivo_nombre"] or "")
                for f in filas]

    def confirmar_mensajes(self, ids: list[str]) -> None:
        with self._conectar() as cn:
            cn.execute("SELECT fila.confirmar_mensajes_rrhh(%s::bigint[])", ([int(i) for i in ids],))

    def avisar_lectura(self, mensaje_id: str, texto: str, pide_confirmacion: bool) -> None:
        with self._conectar() as cn:
            cn.execute("SELECT fila.avisar_lectura_certificado(%s, %s, %s)",
                       (int(mensaje_id), texto, pide_confirmacion))

    def confirmaciones(self, ids: list[str]) -> dict[str, Confirmacion]:
        with self._conectar() as cn:
            filas = cn.execute("SELECT * FROM fila.confirmaciones_certificados(%s::bigint[])",
                               ([int(i) for i in ids],)).fetchall()
        return {str(f["id"]): Confirmacion(f["confirmacion"], f["confirmacion_vence"], f["correccion"] or "",
                                           f["respondido_en"]) for f in filas}

    def tomar_cvs(self) -> list[CVEntrante]:
        with self._conectar() as cn:
            filas = cn.execute("SELECT * FROM fila.cvs_whatsapp_pendientes(20)").fetchall()
        return [CVEntrante(str(f["id"]), f["telefono"], f["nombre_archivo"], bytes(f["contenido"]), f["tipo"],
                           f["recibido_en"]) for f in filas if f["contenido"] is not None]

    def confirmar_cvs(self, ids: list[str]) -> None:
        with self._conectar() as cn:
            cn.execute("SELECT fila.confirmar_cvs_whatsapp(%s::bigint[])", ([int(i) for i in ids],))

    def recorridos(self) -> list[dict[str, Any]]:
        with self._conectar() as cn:
            filas = cn.execute(
                """SELECT r.id, r.sede, r.nombre, r.activo, r.actualizado_por, r.actualizado_en,
                          (SELECT count(*)::int FROM consulta.telefono_personal tp
                            WHERE tp.recorrido_id = r.id AND tp.activo) AS personas
                     FROM fila.recorrido_micro r ORDER BY r.sede, lower(r.nombre)""").fetchall()
        return [dict(f) for f in filas]

    def guardar_recorrido(self, recorrido_id: int | None, sede: str, nombre: str, activo: bool,
                          actor: str) -> dict[str, Any]:
        try:
            with self._conectar() as cn:
                fila = cn.execute("SELECT * FROM fila.guardar_recorrido_micro(%s, %s, %s, %s, %s)",
                                  (recorrido_id, sede, nombre, activo, actor)).fetchone()
        except psycopg.errors.RaiseException as exc:
            raise ValueError(exc.diag.message_primary or "la base rechazó el recorrido") from exc
        return dict(fila)

    def personal(self) -> list[dict[str, Any]]:
        with self._conectar() as cn:
            filas = cn.execute(
                """SELECT p.telefono, p.legajo, p.nombre, p.empresa, p.recorrido_id,
                          r.nombre AS recorrido, r.sede AS recorrido_sede
                     FROM consulta.telefono_personal p
                     LEFT JOIN fila.recorrido_micro r ON r.id = p.recorrido_id
                    WHERE p.activo ORDER BY p.nombre""").fetchall()
        return [dict(f) for f in filas]

    def asignar_recorrido(self, telefono: str, recorrido_id: int | None, actor: str) -> dict[str, Any]:
        # La función de la base sólo cambia el recorrido y lo deja en el historial del celular.
        try:
            with self._conectar() as cn:
                fila = cn.execute("SELECT * FROM consulta.asignar_recorrido_personal(%s, %s, %s)",
                                  (telefono, recorrido_id, actor)).fetchone()
        except psycopg.errors.RaiseException as exc:
            raise ValueError(exc.diag.message_primary or "la base rechazó el recorrido") from exc
        return {"telefono": fila["telefono"], "recorrido_id": fila["recorrido_id"]}
