"""Verificación opt-in contra PostgreSQL local; CI la omite por marcador."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

from suite_juviar.modulos.rrhh_epp.domain.modelos_mvp import StockInsuficiente
from suite_juviar.modulos.rrhh_epp.mvp import construir


@pytest.mark.local
def test_postgresql_local_impide_sobreventa_con_dos_tablets():
    dsn = os.getenv("SJ_RRHH_EPP_DATABASE_URL", "postgresql:///juviar_suite_local")
    primero = construir(
        entorno="prueba",
        persistencia="postgresql",
        postgres_dsn=dsn,
    )
    segundo = construir(
        entorno="prueba",
        persistencia="postgresql",
        postgres_dsn=dsn,
    )
    item = "SIM-68-03"
    primero.stock.configurar(item, disponible=1, minimo=0)
    barrera = Barrier(2)

    def descontar(stock) -> str:
        barrera.wait()
        try:
            stock.descontar([(item, 1)])
            return "CONFIRMADA"
        except StockInsuficiente:
            return "SIN_STOCK"

    try:
        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            resultados = list(ejecutor.map(descontar, [primero.stock, segundo.stock]))
        assert sorted(resultados) == ["CONFIRMADA", "SIN_STOCK"]
        assert primero.stock.obtener(item).disponible == 0  # type: ignore[union-attr]
    finally:
        primero.stock.configurar(item, disponible=100, minimo=20)


@pytest.mark.local
def test_entrega_stock_y_bitacora_son_atomicos_con_dos_tablets():
    dsn = os.getenv("SJ_RRHH_EPP_DATABASE_URL", "postgresql:///juviar_suite_local")
    primero = construir(entorno="prueba", persistencia="postgresql", postgres_dsn=dsn)
    segundo = construir(entorno="prueba", persistencia="postgresql", postgres_dsn=dsn)
    item = "SIM-68-02"
    primero.stock.configurar(item, disponible=1, minimo=0)
    barrera = Barrier(2)
    ids = [f"LOCAL-{uuid4().hex}", f"LOCAL-{uuid4().hex}"]

    def entregar(datos) -> str:
        contenedor, identificador = datos
        barrera.wait()
        try:
            contenedor.registrar_entrega.ejecutar(
                numero_legajo="1042",
                items=[{"codigo": "68", "item_codigo": item, "cantidad": 1}],
                metodo_firma="TRAZO_TABLET",
                evidencia_firma="data:image/png;base64,AAAA",
                usuario_deposito="1210",
                id_entrega=identificador,
            )
            return "CONFIRMADA"
        except StockInsuficiente:
            return "SIN_STOCK"

    try:
        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            resultados = list(ejecutor.map(entregar, zip((primero, segundo), ids, strict=True)))
        assert sorted(resultados) == ["CONFIRMADA", "SIN_STOCK"]
        assert sum(primero.entregas.obtener(identificador) is not None for identificador in ids) == 1
        assert primero.stock.obtener(item).disponible == 0  # type: ignore[union-attr]
    finally:
        primero.stock.configurar(item, disponible=100, minimo=20)
