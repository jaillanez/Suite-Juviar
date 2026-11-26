"""Personas que suben facturas con PIN, en la misma base que los usuarios de Gestión.

Del PIN y del secreto del link sólo queda el resumen scrypt con sal; las sesiones, por
el SHA-256 del token. Las tablas se crean solas: no hace falta migración.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from ..domain.subida_pin import PersonaSubida, SesionSubida


def _resumen_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _fecha(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor) if valor else None


class SubidaPinSQLite:
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
                CREATE TABLE IF NOT EXISTS subida_persona (
                    id TEXT PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    empresa TEXT NOT NULL,
                    pin TEXT NOT NULL,
                    secreto TEXT NOT NULL,
                    activo INTEGER NOT NULL DEFAULT 1,
                    fallos_seguidos INTEGER NOT NULL DEFAULT 0,
                    fallos_acumulados INTEGER NOT NULL DEFAULT 0,
                    bloqueado_hasta TEXT,
                    link_desactivado INTEGER NOT NULL DEFAULT 0,
                    ultimo_ingreso TEXT,
                    creado_por TEXT NOT NULL,
                    creado_en TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS subida_sesion (
                    token_sha256 TEXT PRIMARY KEY,
                    persona_id TEXT NOT NULL REFERENCES subida_persona(id),
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
    def _armar(fila: sqlite3.Row) -> PersonaSubida:
        return PersonaSubida(
            id=fila["id"], nombre=fila["nombre"], empresas=tuple(fila["empresa"].split(",")),
            activo=bool(fila["activo"]), creado_por=fila["creado_por"],
            creado_en=datetime.fromisoformat(fila["creado_en"]),
            fallos_seguidos=fila["fallos_seguidos"], fallos_acumulados=fila["fallos_acumulados"],
            bloqueado_hasta=_fecha(fila["bloqueado_hasta"]), link_desactivado=bool(fila["link_desactivado"]),
            ultimo_ingreso=_fecha(fila["ultimo_ingreso"]),
        )

    def _ejecutar(self, sql: str, valores: tuple) -> None:
        with self._bloqueo:
            self._cn.execute(sql, valores)
            self._cn.commit()

    def crear(self, persona: PersonaSubida, pin_cifrado: str, secreto_cifrado: str) -> None:
        self._ejecutar(
            "INSERT INTO subida_persona (id, nombre, empresa, pin, secreto, activo, creado_por, creado_en) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (persona.id, persona.nombre, ",".join(persona.empresas), pin_cifrado, secreto_cifrado,
             int(persona.activo), persona.creado_por, persona.creado_en.isoformat()),
        )

    def obtener(self, persona_id: str) -> tuple[PersonaSubida, str, str] | None:
        with self._bloqueo:
            fila = self._cn.execute("SELECT * FROM subida_persona WHERE id=?", (persona_id,)).fetchone()
        return (self._armar(fila), fila["pin"], fila["secreto"]) if fila else None

    def listar(self) -> list[PersonaSubida]:
        with self._bloqueo:
            filas = self._cn.execute("SELECT * FROM subida_persona ORDER BY activo DESC, nombre").fetchall()
        return [self._armar(f) for f in filas]

    def actualizar(self, persona: PersonaSubida) -> None:
        self._ejecutar(
            "UPDATE subida_persona SET nombre=?, empresa=?, activo=?, fallos_seguidos=?, fallos_acumulados=?, "
            "bloqueado_hasta=?, link_desactivado=?, ultimo_ingreso=? WHERE id=?",
            (persona.nombre, ",".join(persona.empresas), int(persona.activo), persona.fallos_seguidos,
             persona.fallos_acumulados, persona.bloqueado_hasta.isoformat() if persona.bloqueado_hasta else None,
             int(persona.link_desactivado), persona.ultimo_ingreso.isoformat() if persona.ultimo_ingreso else None,
             persona.id),
        )

    def cambiar_pin(self, persona_id: str, pin_cifrado: str) -> None:
        self._ejecutar("UPDATE subida_persona SET pin=? WHERE id=?", (pin_cifrado, persona_id))

    def cambiar_secreto(self, persona_id: str, secreto_cifrado: str) -> None:
        self._ejecutar("UPDATE subida_persona SET secreto=? WHERE id=?", (secreto_cifrado, persona_id))

    def guardar_sesion(self, token: str, sesion: SesionSubida) -> None:
        self._ejecutar("INSERT INTO subida_sesion VALUES (?,?,?)",
                       (_resumen_token(token), sesion.persona_id, sesion.vence.isoformat()))

    def obtener_sesion(self, token: str) -> SesionSubida | None:
        with self._bloqueo:
            fila = self._cn.execute(
                "SELECT * FROM subida_sesion WHERE token_sha256=?", (_resumen_token(token),)
            ).fetchone()
        return SesionSubida(fila["persona_id"], datetime.fromisoformat(fila["vence"])) if fila else None

    def borrar_sesion(self, token: str) -> None:
        self._ejecutar("DELETE FROM subida_sesion WHERE token_sha256=?", (_resumen_token(token),))

    def borrar_sesiones_de(self, persona_id: str) -> None:
        with self._bloqueo:
            self._cn.execute("DELETE FROM subida_sesion WHERE persona_id=?", (persona_id,))
            self._cn.execute("DELETE FROM subida_sesion WHERE vence<?", (datetime.now(UTC).isoformat(),))
            self._cn.commit()

    def registrar_evento(self, actor: str, accion: str, detalle: str = "") -> None:
        self._ejecutar(
            "INSERT INTO evento_acceso (momento, actor, accion, detalle) VALUES (?,?,?,?)",
            (datetime.now(UTC).isoformat(), actor, accion, detalle),
        )

    def eventos(self, limite: int = 200) -> list[dict[str, str]]:
        with self._bloqueo:
            filas = self._cn.execute(
                "SELECT momento, actor, accion, detalle FROM evento_acceso "
                "WHERE accion LIKE '%SUBIDA%' ORDER BY id DESC LIMIT ?", (limite,),
            ).fetchall()
        return [dict(f) for f in filas]
