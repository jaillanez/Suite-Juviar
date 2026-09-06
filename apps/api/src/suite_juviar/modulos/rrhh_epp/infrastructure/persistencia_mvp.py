"""Guardado de entregas y bitácora.

Para la prueba se usa SQLite, así la aplicación levanta sin instalar nada.
En producción esto va a PostgreSQL (la base propia de la suite). El SQL es
casi el mismo; lo que importa es que el resto del módulo sólo conoce los
puertos, no esta clase.

Deuda técnica anotada: SQLite no soporta la concurrencia de varias tablets
entregando a la vez. Antes de poner esto en un depósito real hay que pasar a
PostgreSQL.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

from ..domain.modelos_mvp import DocumentoConstancia, Entrega, Firma, Legajo, LineaEntrega

ESQUEMA = """
CREATE TABLE IF NOT EXISTS entrega_epp (
    id                TEXT PRIMARY KEY,
    legajo            TEXT NOT NULL,
    fecha_entrega     TEXT NOT NULL,
    usuario_deposito  TEXT NOT NULL,
    circuito          TEXT NOT NULL DEFAULT 'ESPONTANEA',
    motivo            TEXT NOT NULL DEFAULT 'DESGASTE',
    observaciones     TEXT NOT NULL DEFAULT '',
    firma_metodo      TEXT NOT NULL,
    firma_evidencia   TEXT NOT NULL,
    firma_sello       TEXT NOT NULL,
    firma_simulada    INTEGER NOT NULL,
    cabecera_json     TEXT NOT NULL,
    lineas_json       TEXT NOT NULL,
    creado_en         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_entrega_legajo ON entrega_epp (legajo);

CREATE TABLE IF NOT EXISTS constancia_original (
    id_entrega   TEXT PRIMARY KEY REFERENCES entrega_epp(id),
    contenido    BLOB NOT NULL,
    sha256       TEXT NOT NULL,
    generado_en  TEXT NOT NULL,
    firmado      INTEGER NOT NULL,
    simulado     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bitacora (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    momento   TEXT NOT NULL,
    evento    TEXT NOT NULL,
    usuario   TEXT NOT NULL,
    detalle   TEXT NOT NULL
);
"""


def _conectar(ruta: str) -> sqlite3.Connection:
    cn = sqlite3.connect(ruta, check_same_thread=False)
    cn.row_factory = sqlite3.Row
    cn.execute("PRAGMA journal_mode=WAL")
    return cn


class BaseLocal:
    """Conexión compartida por los dos repositorios de abajo."""

    def __init__(self, ruta: str | Path = "datos/entregas_prueba.sqlite3") -> None:
        ruta = str(ruta)
        if ruta != ":memory:":
            Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        self.cn = _conectar(ruta)
        self.cn.executescript(ESQUEMA)
        columnas = {
            fila[1] for fila in self.cn.execute("PRAGMA table_info(entrega_epp)").fetchall()
        }
        if "circuito" not in columnas:
            self.cn.execute(
                "ALTER TABLE entrega_epp ADD COLUMN circuito TEXT NOT NULL DEFAULT 'ESPONTANEA'"
            )
        if "motivo" not in columnas:
            self.cn.execute(
                "ALTER TABLE entrega_epp ADD COLUMN motivo TEXT NOT NULL DEFAULT 'DESGASTE'"
            )
        self.cn.commit()


class EntregasSQLite:
    def __init__(self, base: BaseLocal) -> None:
        self._cn = base.cn

    def guardar(self, entrega: Entrega) -> bool:
        try:
            self._cn.execute(
                """INSERT INTO entrega_epp
                   (id, legajo, fecha_entrega, usuario_deposito, circuito, motivo, observaciones,
                    firma_metodo, firma_evidencia, firma_sello, firma_simulada,
                    cabecera_json, lineas_json, creado_en)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    entrega.id,
                    entrega.legajo.legajo,
                    entrega.fecha_entrega.isoformat(),
                    entrega.usuario_deposito,
                    entrega.circuito,
                    entrega.motivo,
                    entrega.observaciones,
                    entrega.firma_trabajador.metodo,
                    entrega.firma_trabajador.evidencia,
                    entrega.firma_trabajador.sello_tiempo.isoformat(),
                    int(entrega.firma_trabajador.simulada),
                    json.dumps(entrega.legajo.__dict__, ensure_ascii=False),
                    json.dumps([l.__dict__ for l in entrega.lineas], ensure_ascii=False),
                    datetime.now(UTC).isoformat(timespec="seconds"),
                ),
            )
        except sqlite3.IntegrityError:
            self._cn.rollback()
            if self.obtener(entrega.id) is not None:
                return False
            raise
        self._cn.commit()
        return True

    @staticmethod
    def _a_entrega(fila: sqlite3.Row) -> Entrega:
        cabecera = json.loads(fila["cabecera_json"])
        lineas = [LineaEntrega(**l) for l in json.loads(fila["lineas_json"])]
        return Entrega(
            id=fila["id"],
            legajo=Legajo(**cabecera),
            lineas=tuple(lineas),
            fecha_entrega=date.fromisoformat(fila["fecha_entrega"]),
            firma_trabajador=Firma(
                metodo=fila["firma_metodo"],
                evidencia=fila["firma_evidencia"],
                sello_tiempo=datetime.fromisoformat(fila["firma_sello"]),
                simulada=bool(fila["firma_simulada"]),
            ),
            usuario_deposito=fila["usuario_deposito"],
            circuito=fila["circuito"],
            motivo=fila["motivo"],
            observaciones=fila["observaciones"],
        )

    def obtener(self, id_entrega: str) -> Entrega | None:
        fila = self._cn.execute(
            "SELECT * FROM entrega_epp WHERE id = ?", (id_entrega,)
        ).fetchone()
        return self._a_entrega(fila) if fila else None

    def listar_por_legajo(self, legajo: str) -> list[Entrega]:
        filas = self._cn.execute(
            "SELECT * FROM entrega_epp WHERE legajo = ? ORDER BY fecha_entrega DESC, creado_en DESC",
            (str(legajo),),
        ).fetchall()
        return [self._a_entrega(f) for f in filas]


class BitacoraSQLite:
    def __init__(self, base: BaseLocal) -> None:
        self._cn = base.cn

    def registrar(self, evento: str, usuario: str, detalle: dict) -> None:
        self._cn.execute(
            "INSERT INTO bitacora (momento, evento, usuario, detalle) VALUES (?,?,?,?)",
            (
                datetime.now(UTC).isoformat(timespec="seconds"),
                evento,
                usuario,
                json.dumps(detalle, ensure_ascii=False),
            ),
        )
        self._cn.commit()

    def ultimos(self, cantidad: int = 50) -> list[dict]:
        filas = self._cn.execute(
            "SELECT momento, evento, usuario, detalle FROM bitacora ORDER BY id DESC LIMIT ?",
            (cantidad,),
        ).fetchall()
        return [
            {
                "momento": f["momento"],
                "evento": f["evento"],
                "usuario": f["usuario"],
                "detalle": json.loads(f["detalle"]),
            }
            for f in filas
        ]


class ConstanciasSQLite:
    def __init__(self, base: BaseLocal) -> None:
        self._cn = base.cn

    def obtener(self, id_entrega: str) -> DocumentoConstancia | None:
        fila = self._cn.execute(
            "SELECT * FROM constancia_original WHERE id_entrega = ?",
            (id_entrega,),
        ).fetchone()
        if fila is None:
            return None
        return DocumentoConstancia(
            id_entrega=fila["id_entrega"],
            contenido=bytes(fila["contenido"]),
            sha256=fila["sha256"],
            generado_en=datetime.fromisoformat(fila["generado_en"]),
            firmado=bool(fila["firmado"]),
            simulado=bool(fila["simulado"]),
        )

    def guardar_original(self, documento: DocumentoConstancia) -> None:
        self._cn.execute(
            """INSERT OR IGNORE INTO constancia_original
               (id_entrega, contenido, sha256, generado_en, firmado, simulado)
               VALUES (?,?,?,?,?,?)""",
            (
                documento.id_entrega,
                documento.contenido,
                documento.sha256,
                documento.generado_en.isoformat(),
                int(documento.firmado),
                int(documento.simulado),
            ),
        )
        self._cn.commit()
