"""Persistencia durable en Suite y publicación de la copia mínima a DMZ."""

from __future__ import annotations

from datetime import datetime

import psycopg
from psycopg.rows import dict_row

from .modelo import AUSENTE, COLUMNAS_DESTINO
from .planificador import EstadoLocal, Plan

_COLUMNAS = ", ".join(COLUMNAS_DESTINO)
_PARAMETROS = ", ".join(f"%({columna})s" for columna in COLUMNAS_DESTINO)
_ASIGNACIONES = ", ".join(
    f"{columna} = %({columna})s" for columna in COLUMNAS_DESTINO if columna != "ciu"
)


class RepositorioSuite:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def conectar(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, row_factory=dict_row)

    @staticmethod
    def tomar_candado(conexion: psycopg.Connection, sede: str) -> bool:
        fila = conexion.execute(
            "SELECT pg_try_advisory_lock(hashtext(%s)) AS ok", (f"recepcion:{sede}",)
        ).fetchone()
        return bool(fila["ok"])

    @staticmethod
    def estado_local(
        conexion: psycopg.Connection, sede: str, desde: datetime
    ) -> dict[str, EstadoLocal]:
        filas = conexion.execute(
            """SELECT ciu, huella_origen, estado FROM recepcion.descarga
               WHERE sede = %s AND (fecha >= %s OR fecha IS NULL)""",
            (sede, desde),
        ).fetchall()
        return {
            fila["ciu"]: EstadoLocal(fila["ciu"], fila["huella_origen"], fila["estado"])
            for fila in filas
        }

    @staticmethod
    def abrir_corrida(conexion: psycopg.Connection, sede: str, modo: str, desde: datetime) -> int:
        fila = conexion.execute(
            """INSERT INTO recepcion.corrida (sede, modo, ventana_desde)
               VALUES (%s, %s, %s) RETURNING id""",
            (sede, modo, desde),
        ).fetchone()
        conexion.commit()
        return fila["id"]

    @staticmethod
    def cerrar_corrida(
        conexion: psycopg.Connection,
        corrida_id: int,
        leidas: int,
        plan: Plan | None,
        error: str | None,
    ) -> None:
        conexion.execute(
            """UPDATE recepcion.corrida SET
                   fin = now(), leidas = %s, nuevas = %s, modificadas = %s,
                   ausentes = %s, aviso = %s, error = %s
               WHERE id = %s""",
            (
                leidas,
                len(plan.nuevos) if plan else None,
                len(plan.modificados) if plan else None,
                len(plan.ausentes) if plan else None,
                plan.ausencias_suspendidas if plan else None,
                error,
                corrida_id,
            ),
        )
        conexion.commit()

    @staticmethod
    def aplicar(conexion: psycopg.Connection, sede: str, plan: Plan) -> None:
        with conexion.transaction():
            for fila in plan.nuevos:
                conexion.execute(
                    f"""INSERT INTO recepcion.descarga
                            (sede, {_COLUMNAS}, estado, huella_origen, pendiente_publicar)
                        VALUES (%(sede)s, {_PARAMETROS}, %(estado)s, %(huella)s, true)""",
                    {
                        **fila.valores,
                        "sede": sede,
                        "estado": fila.estado,
                        "huella": fila.huella,
                    },
                )
            for fila in plan.modificados:
                conexion.execute(
                    """INSERT INTO recepcion.descarga_cambio
                           (descarga_id, huella_anterior, huella_nueva, valores_anteriores)
                       SELECT id, huella_origen, %(huella)s, to_jsonb(d.*)
                       FROM recepcion.descarga d
                       WHERE sede = %(sede)s AND ciu = %(ciu)s""",
                    {"sede": sede, "ciu": fila.ciu, "huella": fila.huella},
                )
                conexion.execute(
                    f"""UPDATE recepcion.descarga SET
                            {_ASIGNACIONES}, estado = %(estado)s,
                            huella_origen = %(huella)s, ultima_vez_visto = now(),
                            actualizado_en = now(), pendiente_publicar = true
                        WHERE sede = %(sede)s AND ciu = %(ciu)s""",
                    {
                        **fila.valores,
                        "sede": sede,
                        "estado": fila.estado,
                        "huella": fila.huella,
                    },
                )
            if plan.sin_cambio:
                conexion.execute(
                    """UPDATE recepcion.descarga SET ultima_vez_visto = now()
                       WHERE sede = %s AND ciu = ANY(%s)""",
                    (sede, plan.sin_cambio),
                )
            if plan.ausentes:
                conexion.execute(
                    """UPDATE recepcion.descarga SET estado = %s,
                           actualizado_en = now(), pendiente_publicar = true
                       WHERE sede = %s AND ciu = ANY(%s)""",
                    (AUSENTE, sede, plan.ausentes),
                )

    @staticmethod
    def pendientes_de_publicar(conexion: psycopg.Connection, limite: int = 5000) -> list[dict]:
        return conexion.execute(
            """SELECT id, sede, ciu, fecha, nroinscripto, neto, descvariedad,
                      azucar, estado, actualizado_en
               FROM recepcion.descarga WHERE pendiente_publicar
               ORDER BY id LIMIT %s""",
            (limite,),
        ).fetchall()

    @staticmethod
    def marcar_publicadas(conexion: psycopg.Connection, ids: list[int]) -> None:
        conexion.execute(
            "UPDATE recepcion.descarga SET pendiente_publicar = false WHERE id = ANY(%s)",
            (ids,),
        )
        conexion.commit()


class RepositorioDmz:
    """Copia sin CUIT, chofer ni cliente, destinada exclusivamente al bot."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def publicar(self, filas: list[dict]) -> None:
        if not filas:
            return
        with (
            psycopg.connect(self._dsn) as conexion,
            conexion.transaction(),
            conexion.cursor() as cursor,
        ):
            cursor.executemany(
                """INSERT INTO consulta.descarga_publica
                           (sede, ciu, fecha, nroinscripto, neto, variedad, azucar,
                            estado, actualizado_en)
                       VALUES
                           (%(sede)s, %(ciu)s, %(fecha)s, %(nroinscripto)s, %(neto)s,
                            %(descvariedad)s, %(azucar)s, %(estado)s, %(actualizado_en)s)
                       ON CONFLICT (sede, ciu) DO UPDATE SET
                           fecha = EXCLUDED.fecha,
                           nroinscripto = EXCLUDED.nroinscripto,
                           neto = EXCLUDED.neto,
                           variedad = EXCLUDED.variedad,
                           azucar = EXCLUDED.azucar,
                           estado = EXCLUDED.estado,
                           actualizado_en = EXCLUDED.actualizado_en""",
                filas,
            )

    def registrar_sincronizacion(self, sede: str, momento: datetime) -> None:
        with psycopg.connect(self._dsn) as conexion:
            conexion.execute(
                """INSERT INTO consulta.sincronizacion (sede, ultima_ok)
                   VALUES (%s, %s)
                   ON CONFLICT (sede) DO UPDATE SET ultima_ok = EXCLUDED.ultima_ok""",
                (sede, momento),
            )
