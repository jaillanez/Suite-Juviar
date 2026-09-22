"""Persistencia de la cola con privilegios separados para webhook y worker."""

from __future__ import annotations

from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row

from .meta import MensajeEntrante


class RepositorioWebhook:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def encolar(self, mensaje: MensajeEntrante) -> bool:
        with psycopg.connect(self._dsn) as conexion:
            fila = conexion.execute(
                """
                SELECT consulta.encolar_bot(%s, %s, %s, %s, %s) AS insertado
                """,
                (
                    mensaje.wamid,
                    mensaje.telefono,
                    mensaje.tipo,
                    mensaje.texto,
                    mensaje.enviado_en,
                ),
            ).fetchone()
        return bool(fila[0])


@dataclass(frozen=True)
class Pendiente:
    id: int
    telefono: str
    texto: str | None
    intentos: int


class RepositorioBot:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _conexion(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, row_factory=dict_row, autocommit=True)

    def tomar(self, lote: int = 20) -> list[Pendiente]:
        with self._conexion() as conexion:
            filas = conexion.execute(
                """
                UPDATE consulta.bot_entrada SET estado = 'tomado', tomado_en = now()
                WHERE id IN (
                    SELECT id FROM consulta.bot_entrada
                    WHERE estado = 'pendiente'
                       OR (estado = 'tomado' AND tomado_en < now() - interval '2 minutes')
                    ORDER BY recibido_en
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                )
                RETURNING id, telefono, texto, intentos
                """,
                (lote,),
            ).fetchall()
        return [Pendiente(**fila) for fila in filas]

    def productores(self, telefono: str) -> list[str]:
        with self._conexion() as conexion:
            filas = conexion.execute(
                """SELECT clientecuit FROM consulta.telefono_productor
                   WHERE telefono = %s AND activo
                     AND 'ver_informes' = ANY(tareas)
                   ORDER BY clientecuit""",
                (telefono,),
            ).fetchall()
        return [fila["clientecuit"] for fila in filas]

    def respuestas_ultima_hora(self, telefono: str) -> int:
        with self._conexion() as conexion:
            fila = conexion.execute(
                """SELECT count(*) AS n FROM consulta.bot_entrada
                   WHERE telefono = %s AND estado = 'respondido'
                     AND procesado_en > now() - interval '1 hour'""",
                (telefono,),
            ).fetchone()
        return fila["n"]

    def cerrar(
        self,
        id_: int,
        estado: str,
        respuesta: str | None = None,
        wamid_salida: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._conexion() as conexion:
            conexion.execute(
                """UPDATE consulta.bot_entrada SET estado = %s, respuesta = %s,
                       wamid_salida = %s, error = %s, procesado_en = now()
                   WHERE id = %s""",
                (estado, respuesta, wamid_salida, error, id_),
            )

    def reintentar(self, id_: int, error: str, maximo: int) -> None:
        with self._conexion() as conexion:
            conexion.execute(
                """UPDATE consulta.bot_entrada SET intentos = intentos + 1,
                       error = %s, tomado_en = NULL,
                       estado = CASE WHEN intentos + 1 >= %s
                                    THEN 'error' ELSE 'pendiente' END,
                       procesado_en = CASE WHEN intentos + 1 >= %s
                                          THEN now() ELSE NULL END
                   WHERE id = %s""",
                (error[:1000], maximo, maximo, id_),
            )

    def registrar_consulta(self, clientecuit: str, recurso: str, filas: int) -> None:
        with self._conexion() as conexion:
            conexion.execute(
                """INSERT INTO consulta.bitacora_consulta
                       (cliente, clientecuit, recurso, filas)
                   VALUES ('bot-whatsapp', %s, %s, %s)""",
                (clientecuit, recurso, filas),
            )
