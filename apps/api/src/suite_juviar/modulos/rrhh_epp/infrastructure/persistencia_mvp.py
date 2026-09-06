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
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from ..domain.modelos_mvp import (
    DocumentoConstancia,
    Entrega,
    Firma,
    Legajo,
    LineaEntrega,
    StockInsuficiente,
    StockInvalido,
    StockItem,
)

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
    simulado     INTEGER NOT NULL,
    version      INTEGER NOT NULL DEFAULT 1,
    anula_a      TEXT,
    entregas_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS stock_item (
    item_codigo  TEXT PRIMARY KEY,
    disponible  INTEGER NOT NULL CHECK (disponible >= 0),
    minimo      INTEGER NOT NULL CHECK (minimo >= 0),
    estado      TEXT NOT NULL,
    dueno_dato  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aviso_compras (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    item_codigo  TEXT NOT NULL,
    disponible   INTEGER NOT NULL,
    minimo       INTEGER NOT NULL,
    creado_en    TEXT NOT NULL,
    estado       TEXT NOT NULL DEFAULT 'PENDIENTE',
    intentos     INTEGER NOT NULL DEFAULT 0,
    ultimo_error TEXT,
    enviado_en   TEXT,
    procesando_en TEXT
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
        columnas_constancia = {
            fila[1] for fila in self.cn.execute("PRAGMA table_info(constancia_original)").fetchall()
        }
        if "version" not in columnas_constancia:
            self.cn.execute(
                "ALTER TABLE constancia_original ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
            )
        if "anula_a" not in columnas_constancia:
            self.cn.execute("ALTER TABLE constancia_original ADD COLUMN anula_a TEXT")
        if "entregas_json" not in columnas_constancia:
            self.cn.execute(
                "ALTER TABLE constancia_original ADD COLUMN entregas_json TEXT NOT NULL DEFAULT '[]'"
            )
        columnas_aviso = {
            fila[1] for fila in self.cn.execute("PRAGMA table_info(aviso_compras)").fetchall()
        }
        for nombre, definicion in (
            ("intentos", "INTEGER NOT NULL DEFAULT 0"),
            ("ultimo_error", "TEXT"),
            ("enviado_en", "TEXT"),
            ("procesando_en", "TEXT"),
        ):
            if nombre not in columnas_aviso:
                self.cn.execute(f"ALTER TABLE aviso_compras ADD COLUMN {nombre} {definicion}")
        self.cn.commit()


class EntregasSQLite:
    def __init__(self, base: BaseLocal) -> None:
        self._cn = base.cn

    def guardar(self, entrega: Entrega, *, confirmar: bool = True) -> bool:
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
        if confirmar:
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
        fila = self._cn.execute("SELECT * FROM entrega_epp WHERE id = ?", (id_entrega,)).fetchone()
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

    def registrar(
        self,
        evento: str,
        usuario: str,
        detalle: dict,
        *,
        confirmar: bool = True,
    ) -> None:
        self._cn.execute(
            "INSERT INTO bitacora (momento, evento, usuario, detalle) VALUES (?,?,?,?)",
            (
                datetime.now(UTC).isoformat(timespec="seconds"),
                evento,
                usuario,
                json.dumps(detalle, ensure_ascii=False),
            ),
        )
        if confirmar:
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
            version=int(fila["version"]),
            anula_a=fila["anula_a"],
            entregas_incluidas=tuple(json.loads(fila["entregas_json"])),
        )

    def guardar_original(self, documento: DocumentoConstancia) -> None:
        self._cn.execute(
            """INSERT OR IGNORE INTO constancia_original
               (id_entrega, contenido, sha256, generado_en, firmado, simulado,
                version, anula_a, entregas_json)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                documento.id_entrega,
                documento.contenido,
                documento.sha256,
                documento.generado_en.isoformat(),
                int(documento.firmado),
                int(documento.simulado),
                documento.version,
                documento.anula_a,
                json.dumps(documento.entregas_incluidas),
            ),
        )
        self._cn.commit()


class StockSQLite:
    def __init__(self, base: BaseLocal, ruta_inicial: str | Path) -> None:
        self._cn = base.cn
        datos = yaml.safe_load(Path(ruta_inicial).read_text(encoding="utf-8")) or {}
        self._estado = str(datos.get("estado") or "DESCONOCIDO")
        self._dueno_dato = str(datos.get("dueno_dato") or "SIN_DEFINIR")
        for fila in datos.get("stock") or []:
            self._cn.execute(
                """INSERT OR IGNORE INTO stock_item
                   (item_codigo, disponible, minimo, estado, dueno_dato) VALUES (?,?,?,?,?)""",
                (
                    str(fila["item_codigo"]),
                    int(fila["disponible"]),
                    int(fila["minimo"]),
                    str(fila.get("estado") or self._estado),
                    self._dueno_dato,
                ),
            )
        self._cn.commit()

    @property
    def estado(self) -> str:
        return self._estado

    @property
    def dueno_dato(self) -> str:
        return self._dueno_dato

    @staticmethod
    def _a_stock(fila: sqlite3.Row) -> StockItem:
        return StockItem(
            item_codigo=fila["item_codigo"],
            disponible=int(fila["disponible"]),
            minimo=int(fila["minimo"]),
            estado=fila["estado"],
        )

    def listar(self) -> list[StockItem]:
        filas = self._cn.execute("SELECT * FROM stock_item ORDER BY item_codigo").fetchall()
        return [self._a_stock(fila) for fila in filas]

    def obtener(self, item_codigo: str) -> StockItem | None:
        fila = self._cn.execute(
            "SELECT * FROM stock_item WHERE item_codigo = ?", (item_codigo,)
        ).fetchone()
        return self._a_stock(fila) if fila else None

    def verificar(self, lineas: list[tuple[str, int]]) -> None:
        cantidades: dict[str, int] = defaultdict(int)
        for item_codigo, cantidad in lineas:
            cantidades[item_codigo] += cantidad
        for item_codigo, cantidad in cantidades.items():
            stock = self.obtener(item_codigo)
            if stock is None or stock.disponible < cantidad:
                raise StockInsuficiente(
                    f"Stock insuficiente para {item_codigo}: "
                    f"disponible {stock.disponible if stock else 0}, solicitado {cantidad}."
                )

    def descontar(self, lineas: list[tuple[str, int]], *, confirmar: bool = True) -> None:
        self.verificar(lineas)
        cantidades: dict[str, int] = defaultdict(int)
        for item_codigo, cantidad in lineas:
            cantidades[item_codigo] += cantidad
        for item_codigo, cantidad in cantidades.items():
            self._cn.execute(
                "UPDATE stock_item SET disponible = disponible - ? WHERE item_codigo = ?",
                (cantidad, item_codigo),
            )
            stock = self.obtener(item_codigo)
            if stock and stock.disponible <= stock.minimo:
                self._cn.execute(
                    """INSERT INTO aviso_compras
                       (item_codigo, disponible, minimo, creado_en, estado)
                       SELECT ?,?,?,?,'PENDIENTE'
                       WHERE NOT EXISTS (
                           SELECT 1 FROM aviso_compras
                           WHERE item_codigo = ? AND estado IN ('PENDIENTE', 'PROCESANDO')
                       )""",
                    (
                        item_codigo,
                        stock.disponible,
                        stock.minimo,
                        datetime.now(UTC).isoformat(),
                        item_codigo,
                    ),
                )
        if confirmar:
            self._cn.commit()

    def configurar(self, item_codigo: str, disponible: int, minimo: int) -> StockItem:
        if isinstance(disponible, bool) or isinstance(minimo, bool) or disponible < 0 or minimo < 0:
            raise StockInvalido("Disponible y mínimo deben ser enteros mayores o iguales a cero.")
        if self.obtener(item_codigo) is None:
            raise StockInvalido(f"El ítem {item_codigo or '(vacío)'} no existe en el stock.")
        self._cn.execute(
            """UPDATE stock_item SET disponible = ?, minimo = ?, estado = 'CONFIGURADO_DEPOSITO'
               WHERE item_codigo = ?""",
            (disponible, minimo, item_codigo),
        )
        self._cn.commit()
        return self.obtener(item_codigo)  # type: ignore[return-value]

    def alertas_pendientes(self) -> list[dict[str, object]]:
        filas = self._cn.execute(
            "SELECT * FROM aviso_compras WHERE estado = 'PENDIENTE' ORDER BY id"
        ).fetchall()
        return [dict(fila) for fila in filas]

    def reclamar_alertas(self, limite: int = 20) -> list[dict[str, object]]:
        self._cn.execute("BEGIN IMMEDIATE")
        try:
            ahora = datetime.now(UTC)
            vencido = datetime.fromtimestamp(ahora.timestamp() - 900, UTC).isoformat()
            filas = self._cn.execute(
                """SELECT * FROM aviso_compras
                   WHERE estado = 'PENDIENTE'
                      OR (estado = 'PROCESANDO' AND procesando_en < ?)
                   ORDER BY id LIMIT ?""",
                (vencido, limite),
            ).fetchall()
            ids = [int(fila["id"]) for fila in filas]
            self._cn.executemany(
                "UPDATE aviso_compras SET estado = 'PROCESANDO', procesando_en = ? WHERE id = ?",
                [(ahora.isoformat(), aviso_id) for aviso_id in ids],
            )
            self._cn.commit()
            return [dict(fila) for fila in filas]
        except Exception:
            self._cn.rollback()
            raise

    def confirmar_alerta(self, aviso_id: int) -> None:
        self._cn.execute(
            "UPDATE aviso_compras SET estado = 'ENVIADO', enviado_en = ?, "
            "procesando_en = NULL, ultimo_error = NULL "
            "WHERE id = ? AND estado = 'PROCESANDO'",
            (datetime.now(UTC).isoformat(), aviso_id),
        )
        self._cn.commit()

    def reintentar_alerta(self, aviso_id: int, error: str) -> None:
        self._cn.execute(
            "UPDATE aviso_compras SET estado = 'PENDIENTE', procesando_en = NULL, "
            "intentos = intentos + 1, ultimo_error = ? "
            "WHERE id = ? AND estado = 'PROCESANDO'",
            (error[:1000], aviso_id),
        )
        self._cn.commit()


class ConfirmadorEntregaSQLite:
    def __init__(
        self,
        base: BaseLocal,
        entregas: EntregasSQLite,
        stock: StockSQLite,
        bitacora: BitacoraSQLite,
    ) -> None:
        self._cn = base.cn
        self._entregas = entregas
        self._stock = stock
        self._bitacora = bitacora

    def confirmar(
        self,
        entrega: Entrega,
        movimientos_stock: list[tuple[str, int]],
        evento: str,
        usuario: str,
        detalle: dict,
    ) -> bool:
        try:
            self._cn.execute("BEGIN IMMEDIATE")
            if not self._entregas.guardar(entrega, confirmar=False):
                return False
            self._stock.descontar(movimientos_stock, confirmar=False)
            self._bitacora.registrar(evento, usuario, detalle, confirmar=False)
            self._cn.commit()
            return True
        except Exception:
            self._cn.rollback()
            raise
