from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..domain.modelos import MovimientoEPP


class FuenteEntregasSimulada:
    simulada = True

    def __init__(self, movimientos: list[MovimientoEPP] | None = None):
        self._movimientos = list(movimientos or [])

    def listar(self, desde: date, hasta: date) -> list[MovimientoEPP]:
        return [m for m in self._movimientos if desde <= m.fecha <= hasta]


class FuenteEntregasDesdePuerto:
    """Proyección de sólo lectura sobre el repositorio de RRHH/EPP inyectado."""

    def __init__(self, repositorio):
        self._repositorio = repositorio

    @property
    def simulada(self) -> bool:
        return any(
            linea.item_codigo.startswith("SIM-")
            for entrega in self._repositorio.listar_periodo(date.min, date.max)
            for linea in entrega.lineas
        )

    def listar(self, desde: date, hasta: date) -> list[MovimientoEPP]:
        return [
            MovimientoEPP(
                entrega.id,
                entrega.fecha_entrega,
                entrega.legajo.legajo,
                entrega.legajo.sector_codigo,
                entrega.legajo.puesto_codigo,
                linea.codigo,
                linea.item_codigo,
                linea.cantidad,
                linea.reclamo_calidad,
            )
            for entrega in self._repositorio.listar_periodo(desde, hasta)
            for linea in entrega.lineas
        ]


class PreciosSimulados:
    dueno_dato = "Compras"
    simulada = True

    def obtener(self, item_codigo: str, fecha: date) -> Decimal | None:
        return None
