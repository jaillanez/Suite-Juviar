"""Adaptadores PostgreSQL del MVP RRHH/EPP.

El módulo usa una base propia de la suite. Esta conexión nunca apunta a Nexus:
Nexus conserva su adaptador separado y de solo lectura.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import psycopg
import yaml
from psycopg.rows import dict_row

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


class EsquemaPostgreSQLFaltante(RuntimeError):
    pass


class BasePostgreSQL:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        try:
            with self.conectar() as cn, cn.cursor() as cur:
                cur.execute("SELECT to_regclass('rrhh_epp.entrega_epp')")
                if cur.fetchone()[0] is None:
                    raise EsquemaPostgreSQLFaltante(
                        "Falta el esquema RRHH/EPP. Ejecute infra/005_rrhh_epp_local.sql "
                        "contra la base de la suite."
                    )
        except psycopg.Error as exc:
            raise EsquemaPostgreSQLFaltante(
                "No se pudo abrir PostgreSQL para RRHH/EPP. Revise "
                "SJ_RRHH_EPP_DATABASE_URL y la base local."
            ) from exc

    def conectar(self, *, filas_dict: bool = False) -> psycopg.Connection:
        return psycopg.connect(self.dsn, row_factory=dict_row if filas_dict else None)


def _datos_entrega(entrega: Entrega) -> tuple[object, ...]:
    return (
        entrega.id,
        entrega.legajo.legajo,
        entrega.fecha_entrega,
        entrega.usuario_deposito,
        entrega.circuito,
        entrega.motivo,
        entrega.observaciones,
        entrega.firma_trabajador.metodo,
        entrega.firma_trabajador.evidencia,
        entrega.firma_trabajador.sello_tiempo,
        entrega.firma_trabajador.simulada,
        json.dumps(entrega.legajo.__dict__, ensure_ascii=False),
        json.dumps([linea.__dict__ for linea in entrega.lineas], ensure_ascii=False),
    )


def _a_entrega(fila: dict[str, object]) -> Entrega:
    cabecera = fila["cabecera_json"]
    lineas = fila["lineas_json"]
    if isinstance(cabecera, str):
        cabecera = json.loads(cabecera)
    if isinstance(lineas, str):
        lineas = json.loads(lineas)
    return Entrega(
        id=str(fila["id"]),
        legajo=Legajo(**cabecera),  # type: ignore[arg-type]
        lineas=tuple(LineaEntrega(**linea) for linea in lineas),  # type: ignore[union-attr]
        fecha_entrega=fila["fecha_entrega"],  # type: ignore[arg-type]
        firma_trabajador=Firma(
            metodo=str(fila["firma_metodo"]),
            evidencia=str(fila["firma_evidencia"]),
            sello_tiempo=fila["firma_sello"],  # type: ignore[arg-type]
            simulada=bool(fila["firma_simulada"]),
        ),
        usuario_deposito=str(fila["usuario_deposito"]),
        circuito=str(fila["circuito"]),
        motivo=str(fila["motivo"]),
        observaciones=str(fila["observaciones"]),
    )


class EntregasPostgreSQL:
    def __init__(self, base: BasePostgreSQL) -> None:
        self._base = base

    def guardar(self, entrega: Entrega) -> bool:
        with self._base.conectar() as cn, cn.cursor() as cur:
            cur.execute(
                """INSERT INTO rrhh_epp.entrega_epp
                   (id, legajo, fecha_entrega, usuario_deposito, circuito, motivo,
                    observaciones, firma_metodo, firma_evidencia, firma_sello,
                    firma_simulada, cabecera_json, lineas_json)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
                   ON CONFLICT (id) DO NOTHING RETURNING id""",
                _datos_entrega(entrega),
            )
            return cur.fetchone() is not None

    def obtener(self, id_entrega: str) -> Entrega | None:
        with self._base.conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_epp.entrega_epp WHERE id = %s", (id_entrega,))
            fila = cur.fetchone()
            return _a_entrega(fila) if fila else None

    def listar_por_legajo(self, legajo: str) -> list[Entrega]:
        with self._base.conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute(
                """SELECT * FROM rrhh_epp.entrega_epp WHERE legajo = %s
                   ORDER BY fecha_entrega DESC, creado_en DESC""",
                (legajo,),
            )
            return [_a_entrega(fila) for fila in cur.fetchall()]


class BitacoraPostgreSQL:
    def __init__(self, base: BasePostgreSQL) -> None:
        self._base = base

    def registrar(self, evento: str, usuario: str, detalle: dict) -> None:
        with self._base.conectar() as cn, cn.cursor() as cur:
            cur.execute(
                """INSERT INTO rrhh_epp.bitacora (evento, usuario, detalle)
                   VALUES (%s,%s,%s::jsonb)""",
                (evento, usuario, json.dumps(detalle, ensure_ascii=False)),
            )

    def ultimos(self, cantidad: int = 50) -> list[dict]:
        with self._base.conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute(
                """SELECT momento, evento, usuario, detalle FROM rrhh_epp.bitacora
                   ORDER BY id DESC LIMIT %s""",
                (cantidad,),
            )
            return list(cur.fetchall())


class ConstanciasPostgreSQL:
    def __init__(self, base: BasePostgreSQL) -> None:
        self._base = base

    def obtener(self, id_entrega: str) -> DocumentoConstancia | None:
        with self._base.conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute(
                "SELECT * FROM rrhh_epp.constancia_original WHERE id_entrega = %s",
                (id_entrega,),
            )
            fila = cur.fetchone()
            if fila is None:
                return None
            return DocumentoConstancia(
                id_entrega=str(fila["id_entrega"]),
                contenido=bytes(fila["contenido"]),
                sha256=str(fila["sha256"]),
                generado_en=fila["generado_en"],  # type: ignore[arg-type]
                firmado=bool(fila["firmado"]),
                simulado=bool(fila["simulado"]),
                version=int(fila["version"]),
                anula_a=str(fila["anula_a"]) if fila["anula_a"] else None,
                entregas_incluidas=tuple(fila["entregas_json"]),
            )

    def guardar_original(self, documento: DocumentoConstancia) -> None:
        with self._base.conectar() as cn, cn.cursor() as cur:
            cur.execute(
                """INSERT INTO rrhh_epp.constancia_original
                   (id_entrega, contenido, sha256, generado_en, firmado, simulado,
                    version, anula_a, entregas_json)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT (id_entrega) DO NOTHING""",
                (
                    documento.id_entrega,
                    documento.contenido,
                    documento.sha256,
                    documento.generado_en,
                    documento.firmado,
                    documento.simulado,
                    documento.version,
                    documento.anula_a,
                    json.dumps(documento.entregas_incluidas),
                ),
            )


class StockPostgreSQL:
    def __init__(self, base: BasePostgreSQL, ruta_inicial: str | Path) -> None:
        self._base = base
        datos = yaml.safe_load(Path(ruta_inicial).read_text(encoding="utf-8")) or {}
        self._estado = str(datos.get("estado") or "DESCONOCIDO")
        self._dueno_dato = str(datos.get("dueno_dato") or "SIN_DEFINIR")
        filas = [
            (
                str(fila["item_codigo"]),
                int(fila["disponible"]),
                int(fila["minimo"]),
                str(fila.get("estado") or self._estado),
                self._dueno_dato,
            )
            for fila in datos.get("stock") or []
        ]
        with self._base.conectar() as cn, cn.cursor() as cur:
            cur.executemany(
                """INSERT INTO rrhh_epp.stock_item
                   (item_codigo, disponible, minimo, estado, dueno_dato)
                   VALUES (%s,%s,%s,%s,%s) ON CONFLICT (item_codigo) DO NOTHING""",
                filas,
            )

    @property
    def estado(self) -> str:
        return self._estado

    @property
    def dueno_dato(self) -> str:
        return self._dueno_dato

    @staticmethod
    def _a_stock(fila: dict[str, object]) -> StockItem:
        return StockItem(
            item_codigo=str(fila["item_codigo"]),
            disponible=int(fila["disponible"]),
            minimo=int(fila["minimo"]),
            estado=str(fila["estado"]),
        )

    def listar(self) -> list[StockItem]:
        with self._base.conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_epp.stock_item ORDER BY item_codigo")
            return [self._a_stock(fila) for fila in cur.fetchall()]

    def obtener(self, item_codigo: str) -> StockItem | None:
        with self._base.conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute(
                "SELECT * FROM rrhh_epp.stock_item WHERE item_codigo = %s",
                (item_codigo,),
            )
            fila = cur.fetchone()
            return self._a_stock(fila) if fila else None

    @staticmethod
    def _agrupar(lineas: list[tuple[str, int]]) -> dict[str, int]:
        cantidades: dict[str, int] = defaultdict(int)
        for item_codigo, cantidad in lineas:
            cantidades[item_codigo] += cantidad
        return dict(cantidades)

    def verificar(self, lineas: list[tuple[str, int]]) -> None:
        for item_codigo, cantidad in self._agrupar(lineas).items():
            stock = self.obtener(item_codigo)
            if stock is None or stock.disponible < cantidad:
                raise StockInsuficiente(
                    f"Stock insuficiente para {item_codigo}: "
                    f"disponible {stock.disponible if stock else 0}, solicitado {cantidad}."
                )

    def descontar(self, lineas: list[tuple[str, int]]) -> None:
        cantidades = self._agrupar(lineas)
        with self._base.conectar(filas_dict=True) as cn, cn.cursor() as cur:
            self._descontar_con_cursor(cur, cantidades)

    @staticmethod
    def _descontar_con_cursor(cur, cantidades: dict[str, int]) -> None:
        stocks: dict[str, dict[str, object]] = {}
        for item_codigo in sorted(cantidades):
            cur.execute(
                "SELECT * FROM rrhh_epp.stock_item WHERE item_codigo = %s FOR UPDATE",
                (item_codigo,),
            )
            fila = cur.fetchone()
            solicitado = cantidades[item_codigo]
            if fila is None or int(fila["disponible"]) < solicitado:
                raise StockInsuficiente(
                    f"Stock insuficiente para {item_codigo}: "
                    f"disponible {int(fila['disponible']) if fila else 0}, "
                    f"solicitado {solicitado}."
                )
            stocks[item_codigo] = fila

        for item_codigo, cantidad in cantidades.items():
            disponible = int(stocks[item_codigo]["disponible"]) - cantidad
            minimo = int(stocks[item_codigo]["minimo"])
            cur.execute(
                "UPDATE rrhh_epp.stock_item SET disponible = %s WHERE item_codigo = %s",
                (disponible, item_codigo),
            )
            if disponible <= minimo:
                cur.execute(
                    """INSERT INTO rrhh_epp.aviso_compras
                       (item_codigo, disponible, minimo)
                       VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (item_codigo, disponible, minimo),
                )

    def configurar(self, item_codigo: str, disponible: int, minimo: int) -> StockItem:
        if (
            isinstance(disponible, bool)
            or isinstance(minimo, bool)
            or disponible < 0
            or minimo < 0
        ):
            raise StockInvalido("Disponible y mínimo deben ser enteros mayores o iguales a cero.")
        with self._base.conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute(
                """UPDATE rrhh_epp.stock_item
                   SET disponible = %s, minimo = %s, estado = 'CONFIGURADO_DEPOSITO'
                   WHERE item_codigo = %s RETURNING *""",
                (disponible, minimo, item_codigo),
            )
            fila = cur.fetchone()
            if fila is None:
                raise StockInvalido(f"El ítem {item_codigo or '(vacío)'} no existe en el stock.")
            return self._a_stock(fila)

    def alertas_pendientes(self) -> list[dict[str, object]]:
        with self._base.conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute(
                """SELECT * FROM rrhh_epp.aviso_compras
                   WHERE estado = 'PENDIENTE' ORDER BY id"""
            )
            return list(cur.fetchall())


class ConfirmadorEntregaPostgreSQL:
    def __init__(self, base: BasePostgreSQL, stock: StockPostgreSQL) -> None:
        self._base = base
        self._stock = stock

    def confirmar(
        self,
        entrega: Entrega,
        movimientos_stock: list[tuple[str, int]],
        evento: str,
        usuario: str,
        detalle: dict,
    ) -> bool:
        with self._base.conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute(
                """INSERT INTO rrhh_epp.entrega_epp
                   (id, legajo, fecha_entrega, usuario_deposito, circuito, motivo,
                    observaciones, firma_metodo, firma_evidencia, firma_sello,
                    firma_simulada, cabecera_json, lineas_json)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
                   ON CONFLICT (id) DO NOTHING RETURNING id""",
                _datos_entrega(entrega),
            )
            if cur.fetchone() is None:
                return False
            self._stock._descontar_con_cursor(
                cur,
                self._stock._agrupar(movimientos_stock),
            )
            cur.execute(
                """INSERT INTO rrhh_epp.bitacora (evento, usuario, detalle)
                   VALUES (%s,%s,%s::jsonb)""",
                (evento, usuario, json.dumps(detalle, ensure_ascii=False)),
            )
            return True
