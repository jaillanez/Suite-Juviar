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
                entrega.motivo,
            )
            for entrega in self._repositorio.listar_periodo(desde, hasta)
            for linea in entrega.lineas
        ]


class PreciosSimulados:
    dueno_dato = "Compras"
    simulada = True

    def obtener(self, item_codigo: str, fecha: date) -> Decimal | None:
        return None


class NombresDesdePuerto:
    """Nombres del catálogo y de la matriz de RRHH/EPP, leídos sin importar ese módulo."""

    def __init__(self, contenedor):
        self._catalogo = contenedor.catalogo
        self._legajos = contenedor.legajos

    def elemento(self, codigo: str) -> str:
        elemento = self._catalogo.obtener_elemento(codigo)
        return elemento.producto if elemento else codigo

    def item(self, codigo: str) -> str:
        item = self._catalogo.obtener_item(codigo)
        if item is None:
            return codigo
        talle = item.talle if item.talle and item.talle != "SIN_DATO" else ""
        return " · ".join(x for x in (item.marca, item.modelo, f"talle {talle}" if talle else "") if x) or codigo

    def sector(self, codigo: str) -> str:
        nombre = self._catalogo.nombre_sector(codigo)
        if nombre and nombre != codigo:
            return nombre
        return next((p.sector for p in self._legajos.listar_activos() if p.sector_codigo == codigo and p.sector),
                    codigo)

    def puesto(self, codigo: str) -> str:
        return next((p.puesto for p in self._legajos.listar_activos() if p.puesto_codigo == codigo and p.puesto),
                    codigo)


class NombresPorCodigo:
    """Sin catálogo conectado: se muestra el código tal cual."""

    def elemento(self, codigo: str) -> str:
        return codigo

    item = sector = puesto = elemento
