"""Colecciones persistentes para adaptadores locales.

No son caches: cada escritura se confirma en un archivo SQLite y sobrevive al
reinicio del proceso. Se usan solamente para el entorno local/prueba; el
despliegue productivo conserva PostgreSQL como destino.
"""

from __future__ import annotations

import pickle
import sqlite3
from collections.abc import Iterator, MutableMapping
from pathlib import Path
from threading import RLock
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class BaseColeccionesSQLite:
    def __init__(self, ruta: str | Path) -> None:
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        self.cn = sqlite3.connect(str(ruta), check_same_thread=False)
        self.cn.execute("PRAGMA journal_mode=WAL")
        self.cn.execute(
            """CREATE TABLE IF NOT EXISTS objeto_persistente (
                   espacio TEXT NOT NULL,
                   clave BLOB NOT NULL,
                   valor BLOB NOT NULL,
                   PRIMARY KEY (espacio, clave)
               )"""
        )
        self.cn.execute(
            """CREATE TABLE IF NOT EXISTS lista_persistente (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   espacio TEXT NOT NULL,
                   valor BLOB NOT NULL
               )"""
        )
        self.cn.commit()
        self.bloqueo = RLock()


class MapaSQLite(MutableMapping[K, V], Generic[K, V]):
    def __init__(self, base: BaseColeccionesSQLite, espacio: str) -> None:
        self._base = base
        self._espacio = espacio

    @staticmethod
    def _serializar(valor) -> bytes:
        return pickle.dumps(valor, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def _leer(valor: bytes):
        return pickle.loads(valor)

    def __getitem__(self, clave: K) -> V:
        with self._base.bloqueo:
            fila = self._base.cn.execute(
                "SELECT valor FROM objeto_persistente WHERE espacio=? AND clave=?",
                (self._espacio, self._serializar(clave)),
            ).fetchone()
        if fila is None:
            raise KeyError(clave)
        return self._leer(fila[0])

    def __setitem__(self, clave: K, valor: V) -> None:
        with self._base.bloqueo:
            self._base.cn.execute(
                """INSERT INTO objeto_persistente (espacio, clave, valor) VALUES (?,?,?)
                   ON CONFLICT (espacio, clave) DO UPDATE SET valor=excluded.valor""",
                (self._espacio, self._serializar(clave), self._serializar(valor)),
            )
            self._base.cn.commit()

    def __delitem__(self, clave: K) -> None:
        with self._base.bloqueo:
            cursor = self._base.cn.execute(
                "DELETE FROM objeto_persistente WHERE espacio=? AND clave=?",
                (self._espacio, self._serializar(clave)),
            )
            self._base.cn.commit()
        if not cursor.rowcount:
            raise KeyError(clave)

    def __iter__(self) -> Iterator[K]:
        with self._base.bloqueo:
            filas = self._base.cn.execute(
                "SELECT clave FROM objeto_persistente WHERE espacio=? ORDER BY rowid",
                (self._espacio,),
            ).fetchall()
        return iter([self._leer(fila[0]) for fila in filas])

    def __len__(self) -> int:
        with self._base.bloqueo:
            return int(self._base.cn.execute(
                "SELECT COUNT(*) FROM objeto_persistente WHERE espacio=?",
                (self._espacio,),
            ).fetchone()[0])


class ListaSQLite(Generic[V]):
    def __init__(self, base: BaseColeccionesSQLite, espacio: str) -> None:
        self._base = base
        self._espacio = espacio

    def append(self, valor: V) -> None:
        with self._base.bloqueo:
            self._base.cn.execute(
                "INSERT INTO lista_persistente (espacio, valor) VALUES (?,?)",
                (self._espacio, pickle.dumps(valor, protocol=pickle.HIGHEST_PROTOCOL)),
            )
            self._base.cn.commit()

    def __iter__(self) -> Iterator[V]:
        with self._base.bloqueo:
            filas = self._base.cn.execute(
                "SELECT valor FROM lista_persistente WHERE espacio=? ORDER BY id",
                (self._espacio,),
            ).fetchall()
        return iter([pickle.loads(fila[0]) for fila in filas])

    def __len__(self) -> int:
        with self._base.bloqueo:
            return int(self._base.cn.execute(
                "SELECT COUNT(*) FROM lista_persistente WHERE espacio=?",
                (self._espacio,),
            ).fetchone()[0])

