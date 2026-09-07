from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

from ..domain.modelos import (
    ComparacionInvalida,
    CostoPersona,
    ExportacionNoPermitida,
    MetricasItem,
    MovimientoEPP,
)
from ..domain.puertos import FuenteEntregas, PrecioItem


class AnalizarEPP:
    def __init__(self, fuente: FuenteEntregas, precios: PrecioItem, muestra_minima: int = 5):
        if muestra_minima < 2:
            raise ValueError("La muestra mínima debe ser al menos 2.")
        self.fuente = fuente
        self.precios = precios
        self.muestra_minima = muestra_minima

    @property
    def datos_simulados(self) -> bool:
        return self.fuente.simulada or self.precios.simulada

    def metricas(self, desde: date, hasta: date) -> list[MetricasItem]:
        movimientos = self.fuente.listar(desde, hasta)
        por_item: dict[tuple[str, str, str], list[MovimientoEPP]] = defaultdict(list)
        for movimiento in movimientos:
            por_item[(movimiento.item_codigo, movimiento.sector, movimiento.puesto)].append(
                movimiento
            )
        salida = []
        for (item, sector, puesto), filas in sorted(por_item.items()):
            fechas: dict[str, list[date]] = defaultdict(list)
            for fila in filas:
                fechas[fila.legajo].append(fila.fecha)
            duraciones = [
                (ordenadas[i] - ordenadas[i - 1]).days
                for valores in fechas.values()
                for ordenadas in [sorted(valores)]
                for i in range(1, len(ordenadas))
            ]
            suficiente = len(filas) >= self.muestra_minima and bool(duraciones)
            salida.append(
                MetricasItem(
                    item_codigo=item,
                    sector=sector,
                    puesto=puesto,
                    consumo=sum(f.cantidad for f in filas),
                    reclamos=dict(Counter(f.reclamo_calidad for f in filas if f.reclamo_calidad)),
                    muestra_duracion=len(filas),
                    duracion_promedio_dias=(sum(duraciones) / len(duraciones) if suficiente else None),
                    estado_duracion="CALCULADO" if suficiente else "SIN_DATOS_SUFICIENTES",
                )
            )
        return salida

    def costos_por_persona(self, desde: date, hasta: date) -> list[CostoPersona]:
        totales: dict[str, Decimal] = defaultdict(Decimal)
        faltantes: set[str] = set()
        personas: set[str] = set()
        for fila in self.fuente.listar(desde, hasta):
            personas.add(fila.legajo)
            precio = self.precios.obtener(fila.item_codigo, fila.fecha)
            if precio is None:
                faltantes.add(fila.legajo)
            else:
                totales[fila.legajo] += precio * fila.cantidad
        return [
            CostoPersona(
                legajo=legajo,
                costo=None if legajo in faltantes else totales[legajo],
                faltante=("Falta precio real de Compras" if legajo in faltantes else None),
            )
            for legajo in sorted(personas)
        ]

    def comparar(self, item_a: str, item_b: str, elemento_por_item: dict[str, str], desde: date, hasta: date):
        if elemento_por_item.get(item_a) != elemento_por_item.get(item_b):
            raise ComparacionInvalida("Sólo se comparan ítems del mismo elemento normativo.")
        metricas = self.metricas(desde, hasta)
        return (
            [m for m in metricas if m.item_codigo == item_a],
            [m for m in metricas if m.item_codigo == item_b],
        )

    def exportar(self, desde: date, hasta: date) -> bytes:
        movimientos = self.fuente.listar(desde, hasta)
        if self.datos_simulados or any(m.item_codigo.startswith("SIM-") for m in movimientos):
            raise ExportacionNoPermitida(
                "Los datos simulados no se pueden exportar como evidencia."
            )
        lineas = ["DATOS REALES — INFORME DE CONSUMO", "item,cantidad"]
        lineas.extend(f"{m.item_codigo},{m.consumo}" for m in self.metricas(desde, hasta))
        return ("\n".join(lineas) + "\n").encode()
