"""Persistencia de la cola con privilegios separados para webhook y worker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg
from psycopg.rows import dict_row

from .archivos import Archivo
from .dialogo import MINUTOS_SESION, Cuenta, Estado
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

    def cuentas(self, telefono: str) -> list[Cuenta]:
        with self._conexion() as conexion:
            filas = conexion.execute(
                """SELECT p.clientecuit,p.razonsocial,p.codigos
                   FROM consulta.telefono_productor t
                   JOIN fila.productor p USING(clientecuit)
                   WHERE t.telefono=%s AND t.activo
                   ORDER BY p.razonsocial""",
                (telefono,),
            ).fetchall()
        return [
            Cuenta(f["clientecuit"], (f["codigos"] or [f["clientecuit"]])[0], f["razonsocial"])
            for f in filas
        ]

    def permisos(self, telefono: str) -> set[str]:
        with self._conexion() as conexion:
            filas = conexion.execute(
                """SELECT unnest(tareas) tarea FROM consulta.telefono_productor
                   WHERE telefono=%s AND activo""",
                (telefono,),
            ).fetchall()
        return {f["tarea"] for f in filas}

    def estado(self, telefono: str, ahora: datetime | None = None) -> Estado:
        return self.estado_y_caducidad(telefono, ahora)[0]

    def estado_y_caducidad(
        self, telefono: str, ahora: datetime | None = None
    ) -> tuple[Estado, bool]:
        ahora = ahora or datetime.now(UTC)
        with self._conexion() as conexion:
            fila = conexion.execute(
                "SELECT paso,clientecuit,pedido,actualizado FROM consulta.bot_sesion WHERE telefono=%s",
                (telefono,),
            ).fetchone()
        if not fila:
            return Estado(), False
        if fila["actualizado"] < ahora - timedelta(minutes=MINUTOS_SESION):
            return Estado(), True
        return Estado(fila["paso"], fila["clientecuit"], fila["pedido"]), False

    def guardar_estado(self, telefono: str, estado: Estado) -> None:
        with self._conexion() as conexion:
            conexion.execute(
                """INSERT INTO consulta.bot_sesion(telefono,paso,clientecuit,pedido)
                   VALUES (%s,%s,%s,%s)
                   ON CONFLICT(telefono) DO UPDATE SET paso=EXCLUDED.paso,
                     clientecuit=EXCLUDED.clientecuit,pedido=EXCLUDED.pedido,actualizado=now()""",
                (telefono, estado.paso, estado.cuenta, estado.pedido),
            )

    def guardar_archivo(self, archivo: Archivo, telefono: str) -> None:
        with self._conexion() as conexion:
            conexion.execute(
                """INSERT INTO consulta.bot_archivo
                   (token,extension,nombre,contenido,telefono,vence)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (
                    archivo.token,
                    archivo.extension,
                    archivo.nombre,
                    archivo.contenido,
                    telefono,
                    archivo.vence,
                ),
            )

    def limpiar_archivos(self) -> int:
        with self._conexion() as conexion:
            resultado = conexion.execute(
                "DELETE FROM consulta.bot_archivo WHERE vence<now()"
            )
        return resultado.rowcount

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


class RepositorioArchivos:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def leer(self, token: str) -> dict | None:
        with psycopg.connect(self._dsn, row_factory=dict_row) as conexion:
            return conexion.execute(
                "SELECT * FROM consulta.leer_archivo(%s)", (token,)
            ).fetchone()
