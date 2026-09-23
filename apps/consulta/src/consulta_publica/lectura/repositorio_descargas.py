"""Repositorio PostgreSQL de solo lectura para el bot."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import psycopg
from consulta_publica.api.descargas import Descarga
from consulta_publica.bot.estadisticas import Entrega
from psycopg.rows import dict_row

_CAMPOS = "sede, ciu, id_origen, fecha, neto, variedad, azucar, estado"
_VISIBLE = "estado <> 'ausente_en_origen'"


class RepositorioDescargasPg:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _consultar(self, sql: str, parametros: tuple) -> list[dict]:
        with psycopg.connect(self._dsn, row_factory=dict_row) as conexion:
            return conexion.execute(sql, parametros).fetchall()

    @staticmethod
    def _descarga(fila: dict) -> Descarga:
        return Descarga(
            fila["sede"],
            fila["ciu"],
            fila["id_origen"],
            fila["fecha"],
            fila["neto"],
            fila["variedad"],
            float(fila["azucar"]) if fila["azucar"] is not None else None,
            fila["estado"],
        )

    def ultima(self, clientecuit: str) -> Descarga | None:
        filas = self._consultar(
            f"""SELECT {_CAMPOS} FROM consulta.descarga_publica
                WHERE clientecuit = %s AND estado = 'descargado'
                ORDER BY fecha DESC LIMIT 1""",
            (clientecuit,),
        )
        return self._descarga(filas[0]) if filas else None

    def del_dia(self, clientecuit: str, dia: date) -> list[Descarga]:
        return [
            self._descarga(fila)
            for fila in self._consultar(
                f"""SELECT {_CAMPOS} FROM consulta.descarga_publica
                    WHERE clientecuit = %s AND estado = 'descargado'
                      AND fecha >= %s AND fecha < %s ORDER BY fecha""",
                (clientecuit, dia, dia + timedelta(days=1)),
            )
        ]

    def en_descarga(self, clientecuit: str) -> list[Descarga]:
        return [
            self._descarga(fila)
            for fila in self._consultar(
                f"""SELECT {_CAMPOS} FROM consulta.descarga_publica
                    WHERE clientecuit = %s AND estado = 'en_descarga'""",
                (clientecuit,),
            )
        ]

    def rango(
        self, clientecuit: str, desde: date, hasta: date, limite: int
    ) -> list[Descarga]:
        return [
            self._descarga(fila)
            for fila in self._consultar(
                f"""SELECT {_CAMPOS} FROM consulta.descarga_publica
                    WHERE clientecuit = %s AND {_VISIBLE}
                      AND fecha >= %s AND fecha < %s
                    ORDER BY fecha DESC LIMIT %s""",
                (clientecuit, desde, hasta + timedelta(days=1), limite),
            )
        ]

    def entregas(self, clientecuit: str, desde: date, hasta: date) -> list[Entrega]:
        filas = self._consultar(
            """SELECT sede,ciu,fecha,variedad,neto,azucar
               FROM consulta.descarga_publica
               WHERE clientecuit=%s AND estado='descargado'
                 AND fecha >= %s AND fecha < %s
               ORDER BY fecha,ciu""",
            (clientecuit, desde, hasta + timedelta(days=1)),
        )
        return [
            Entrega(
                fecha=f["fecha"].date() if isinstance(f["fecha"], datetime) else f["fecha"],
                ciu=f["ciu"],
                variedad=f["variedad"] or "Sin variedad",
                neto=f["neto"] or 0,
                azucar=f["azucar"],
                sede=f["sede"] or "",
            )
            for f in filas
        ]

    def datos_al(self) -> dict[str, datetime]:
        return {
            fila["sede"]: fila["ultima_ok"]
            for fila in self._consultar(
                "SELECT sede, ultima_ok FROM consulta.sincronizacion", ()
            )
        }

    def registrar(
        self, cliente: str, clientecuit: str, recurso: str, filas: int, ip: str | None
    ) -> None:
        with psycopg.connect(self._dsn) as conexion:
            conexion.execute(
                """INSERT INTO consulta.bitacora_consulta
                       (cliente, clientecuit, recurso, filas, ip_origen)
                   VALUES (%s, %s, %s, %s, %s)""",
                (cliente, clientecuit, recurso, filas, ip),
            )
