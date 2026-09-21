"""Adaptador de solo lectura para V_DETALLE_MOVIMIENTOS."""

from __future__ import annotations

import socket
from datetime import datetime

import oracledb

from .config import Sede
from .modelo import COLUMNAS_ORIGEN, FilaOrigen

VISTA = "V_DETALLE_MOVIMIENTOS"


def ipv4(host: str, puerto: int) -> str:
    """Resuelve en cada conexión porque Lavalle utiliza DNS dinámico."""
    return socket.getaddrinfo(host, puerto, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]


class FuenteOracle:
    def __init__(self, sede: Sede, usuario: str, clave: str) -> None:
        self._sede = sede
        self._usuario = usuario
        self._clave = clave

    def conectar(self) -> oracledb.Connection:
        dsn = oracledb.makedsn(
            ipv4(self._sede.host, self._sede.puerto),
            self._sede.puerto,
            service_name=self._sede.servicio,
        )
        return oracledb.connect(
            user=self._usuario,
            password=self._clave,
            dsn=dsn,
            tcp_connect_timeout=15,
        )

    def leer_ventana(self, desde: datetime) -> list[FilaOrigen]:
        sql = (
            f"SELECT {', '.join(COLUMNAS_ORIGEN)} FROM {VISTA} "
            "WHERE FECHA >= :desde OR FECHA IS NULL"
        )
        with self.conectar() as conexion, conexion.cursor() as cursor:
            cursor.arraysize = 1000
            cursor.execute(sql, desde=desde)
            nombres = [descripcion[0] for descripcion in cursor.description]
            return [
                FilaOrigen.desde_oracle(self._sede.codigo, dict(zip(nombres, fila)))
                for fila in cursor
            ]
