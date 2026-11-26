"""Enlaces para recuperar la contraseña y pedidos recientes, en la base de usuarios.

Del código del enlace sólo queda el SHA-256. Las tablas se crean solas: no hace falta
migración.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock


class RecuperacionSQLite:
    def __init__(self, ruta: str | Path) -> None:
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        self._cn = sqlite3.connect(str(ruta), check_same_thread=False)
        self._cn.row_factory = sqlite3.Row
        self._bloqueo = RLock()
        with self._bloqueo:
            self._cn.execute("PRAGMA journal_mode=WAL")
            self._cn.executescript(
                """
                CREATE TABLE IF NOT EXISTS recuperacion_enlace (
                    token_sha256 TEXT PRIMARY KEY,
                    usuario_id TEXT NOT NULL,
                    vence TEXT NOT NULL,
                    creado_en TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS recuperacion_pedido (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    momento TEXT NOT NULL,
                    email TEXT NOT NULL,
                    origen TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS recuperacion_pedido_momento ON recuperacion_pedido(momento);
                """
            )
            self._cn.commit()

    def anotar_pedido_si_hay_cupo(self, email: str, origen: str, ahora: datetime, ventana: timedelta,
                                  por_correo: int, por_origen: int) -> bool:
        """Cuenta y anota el pedido en un solo paso; False si se pasó de alguno de los límites."""
        desde = (ahora - ventana).isoformat()
        with self._bloqueo:
            self._cn.execute("DELETE FROM recuperacion_pedido WHERE momento<?", (desde,))
            del_correo = self._cn.execute(
                "SELECT COUNT(*) FROM recuperacion_pedido WHERE email=? AND momento>=?", (email, desde)
            ).fetchone()[0]
            del_origen = self._cn.execute(
                "SELECT COUNT(*) FROM recuperacion_pedido WHERE origen=? AND momento>=?", (origen, desde)
            ).fetchone()[0]
            hay_cupo = del_correo < por_correo and del_origen < por_origen
            if hay_cupo:
                self._cn.execute(
                    "INSERT INTO recuperacion_pedido (momento, email, origen) VALUES (?,?,?)",
                    (ahora.isoformat(), email, origen),
                )
            self._cn.commit()
        return hay_cupo

    def reemplazar_enlace(self, usuario_id: str, token_sha256: str, vence: datetime, ahora: datetime) -> None:
        """Deja un único enlace vigente por usuario: el nuevo anula los anteriores."""
        with self._bloqueo:
            self._cn.execute("DELETE FROM recuperacion_enlace WHERE usuario_id=? OR vence<?",
                             (usuario_id, ahora.isoformat()))
            self._cn.execute("INSERT INTO recuperacion_enlace VALUES (?,?,?,?)",
                             (token_sha256, usuario_id, vence.isoformat(), ahora.isoformat()))
            self._cn.commit()

    def vigente(self, token_sha256: str, ahora: datetime) -> str | None:
        with self._bloqueo:
            fila = self._cn.execute(
                "SELECT usuario_id FROM recuperacion_enlace WHERE token_sha256=? AND vence>?",
                (token_sha256, ahora.isoformat()),
            ).fetchone()
        return fila["usuario_id"] if fila else None

    def consumir(self, token_sha256: str, ahora: datetime) -> str | None:
        """Borra el enlace y devuelve de quién era, sólo si seguía vigente. Sirve una sola vez."""
        with self._bloqueo:
            fila = self._cn.execute(
                "SELECT usuario_id, vence FROM recuperacion_enlace WHERE token_sha256=?", (token_sha256,)
            ).fetchone()
            self._cn.execute("DELETE FROM recuperacion_enlace WHERE token_sha256=?", (token_sha256,))
            self._cn.commit()
        if fila is None or datetime.fromisoformat(fila["vence"]) <= ahora:
            return None
        return fila["usuario_id"]

    def anular_enlaces_de(self, usuario_id: str) -> None:
        with self._bloqueo:
            self._cn.execute("DELETE FROM recuperacion_enlace WHERE usuario_id=?", (usuario_id,))
            self._cn.commit()
