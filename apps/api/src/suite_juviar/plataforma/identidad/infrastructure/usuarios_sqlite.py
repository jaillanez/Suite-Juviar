"""Cuentas y sesiones de Gestión en SQLite.

Guarda la contraseña ya cifrada y las sesiones por el SHA-256 del token: con una
copia de la base no se puede entrar.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from ..domain.usuarios import SesionGuardada, Usuario


def _resumen_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class UsuariosSQLite:
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
                CREATE TABLE IF NOT EXISTS usuario (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    nombre TEXT NOT NULL,
                    perfil TEXT NOT NULL,
                    empresa TEXT NOT NULL,
                    clave TEXT NOT NULL,
                    activo INTEGER NOT NULL DEFAULT 1,
                    debe_cambiar_clave INTEGER NOT NULL DEFAULT 1,
                    creado_en TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sesion (
                    token_sha256 TEXT PRIMARY KEY,
                    usuario_id TEXT NOT NULL REFERENCES usuario(id),
                    empresa TEXT NOT NULL,
                    vence TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evento_acceso (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    momento TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    accion TEXT NOT NULL,
                    detalle TEXT NOT NULL DEFAULT ''
                );
                """
            )
            self._cn.commit()

    @staticmethod
    def _armar(fila: sqlite3.Row) -> Usuario:
        return Usuario(
            id=fila["id"], email=fila["email"], nombre=fila["nombre"], perfil=fila["perfil"],
            empresa=fila["empresa"], activo=bool(fila["activo"]),
            debe_cambiar_clave=bool(fila["debe_cambiar_clave"]),
            creado_en=datetime.fromisoformat(fila["creado_en"]),
        )

    def crear(self, usuario: Usuario, clave_cifrada: str) -> None:
        with self._bloqueo:
            try:
                self._cn.execute(
                    "INSERT INTO usuario VALUES (?,?,?,?,?,?,?,?,?)",
                    (usuario.id, usuario.email, usuario.nombre, usuario.perfil, usuario.empresa,
                     clave_cifrada, int(usuario.activo), int(usuario.debe_cambiar_clave),
                     usuario.creado_en.isoformat()),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Ya existe un usuario con ese correo.") from exc
            self._cn.commit()

    def obtener(self, usuario_id: str) -> Usuario | None:
        with self._bloqueo:
            fila = self._cn.execute("SELECT * FROM usuario WHERE id=?", (usuario_id,)).fetchone()
        return self._armar(fila) if fila else None

    def obtener_por_email(self, email: str) -> tuple[Usuario, str] | None:
        with self._bloqueo:
            fila = self._cn.execute("SELECT * FROM usuario WHERE email=?", (email,)).fetchone()
        return (self._armar(fila), fila["clave"]) if fila else None

    def listar(self) -> list[Usuario]:
        with self._bloqueo:
            filas = self._cn.execute("SELECT * FROM usuario ORDER BY nombre").fetchall()
        return [self._armar(f) for f in filas]

    def actualizar(self, usuario: Usuario) -> None:
        with self._bloqueo:
            self._cn.execute(
                "UPDATE usuario SET nombre=?, perfil=?, empresa=?, activo=?, debe_cambiar_clave=? "
                "WHERE id=?",
                (usuario.nombre, usuario.perfil, usuario.empresa, int(usuario.activo),
                 int(usuario.debe_cambiar_clave), usuario.id),
            )
            self._cn.commit()

    def cambiar_clave(self, usuario_id: str, clave_cifrada: str, debe_cambiar: bool) -> None:
        with self._bloqueo:
            self._cn.execute(
                "UPDATE usuario SET clave=?, debe_cambiar_clave=? WHERE id=?",
                (clave_cifrada, int(debe_cambiar), usuario_id),
            )
            self._cn.commit()

    def guardar_sesion(self, token: str, sesion: SesionGuardada) -> None:
        with self._bloqueo:
            self._cn.execute(
                "INSERT INTO sesion VALUES (?,?,?,?)",
                (_resumen_token(token), sesion.usuario_id, sesion.empresa, sesion.vence.isoformat()),
            )
            self._cn.commit()

    def obtener_sesion(self, token: str) -> SesionGuardada | None:
        with self._bloqueo:
            fila = self._cn.execute(
                "SELECT * FROM sesion WHERE token_sha256=?", (_resumen_token(token),)
            ).fetchone()
        if fila is None:
            return None
        return SesionGuardada(fila["usuario_id"], fila["empresa"], datetime.fromisoformat(fila["vence"]))

    def cambiar_empresa_sesion(self, token: str, empresa: str) -> None:
        with self._bloqueo:
            self._cn.execute(
                "UPDATE sesion SET empresa=? WHERE token_sha256=?", (empresa, _resumen_token(token))
            )
            self._cn.commit()

    def borrar_sesion(self, token: str) -> None:
        with self._bloqueo:
            self._cn.execute("DELETE FROM sesion WHERE token_sha256=?", (_resumen_token(token),))
            self._cn.commit()

    def borrar_sesiones_de(self, usuario_id: str, salvo_token: str | None = None) -> None:
        with self._bloqueo:
            self._cn.execute(
                "DELETE FROM sesion WHERE usuario_id=? AND token_sha256<>?",
                (usuario_id, _resumen_token(salvo_token) if salvo_token else ""),
            )
            self._cn.execute("DELETE FROM sesion WHERE vence<?", (datetime.now(UTC).isoformat(),))
            self._cn.commit()

    def registrar_evento(self, actor: str, accion: str, detalle: str = "") -> None:
        with self._bloqueo:
            self._cn.execute(
                "INSERT INTO evento_acceso (momento, actor, accion, detalle) VALUES (?,?,?,?)",
                (datetime.now(UTC).isoformat(), actor, accion, detalle),
            )
            self._cn.commit()

    def eventos(self, limite: int = 200) -> list[dict[str, str]]:
        with self._bloqueo:
            filas = self._cn.execute(
                "SELECT momento, actor, accion, detalle FROM evento_acceso ORDER BY id DESC LIMIT ?",
                (limite,),
            ).fetchall()
        return [dict(f) for f in filas]
