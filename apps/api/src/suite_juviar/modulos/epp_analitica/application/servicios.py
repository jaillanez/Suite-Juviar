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
            fechas: dict[str, list[MovimientoEPP]] = defaultdict(list)
            for fila in filas:
                fechas[fila.legajo].append(fila)
            duraciones = [
                (ordenadas[i].fecha - ordenadas[i - 1].fecha).days
                for valores in fechas.values()
                for ordenadas in [sorted(valores, key=lambda f: f.fecha)]
                for i in range(1, len(ordenadas))
                if ordenadas[i].motivo_entrega.upper() in {"ROTURA", "DESGASTE"}
            ]
            suficiente = len(duraciones) >= self.muestra_minima
            reclamos = Counter(f.reclamo_calidad for f in filas if f.reclamo_calidad)
            total_reclamos = sum(reclamos.values())
            salida.append(
                MetricasItem(
                    item_codigo=item,
                    sector=sector,
                    puesto=puesto,
                    consumo=sum(f.cantidad for f in filas),
                    reclamos=dict(reclamos),
                    reclamos_total=total_reclamos,
                    reclamos_proporcion=round(total_reclamos / len(filas), 4),
                    muestra_entregas=len(filas),
                    muestra_duracion=len(duraciones),
                    duracion_promedio_dias=(
                        sum(duraciones) / len(duraciones) if suficiente else None
                    ),
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

    def comparar(self, item_a: str, item_b: str, desde: date, hasta: date):
        movimientos = self.fuente.listar(desde, hasta)
        elementos = {
            codigo: {m.elemento_codigo for m in movimientos if m.item_codigo == codigo}
            for codigo in (item_a, item_b)
        }
        if not elementos[item_a] or not elementos[item_b]:
            raise ComparacionInvalida("Ambos ítems deben tener entregas en el período.")
        if elementos[item_a] != elementos[item_b] or len(elementos[item_a]) != 1:
            raise ComparacionInvalida("Sólo se comparan ítems del mismo elemento normativo.")
        metricas = self.metricas(desde, hasta)
        resultados = {
            codigo: [m for m in metricas if m.item_codigo == codigo] for codigo in (item_a, item_b)
        }
        razones = {
            codigo: (
                None
                if filas and all(f.estado_duracion == "CALCULADO" for f in filas)
                else f"{codigo}: sin datos suficientes; requiere {self.muestra_minima} reposiciones concluyentes"
            )
            for codigo, filas in resultados.items()
        }
        precios = {codigo: self.precios.obtener(codigo, hasta) for codigo in (item_a, item_b)}
        return {
            "habilitado": not any(razones.values()),
            "items": resultados,
            "razones": razones,
            "precios": precios,
            "precio_leyenda": "Faltan precios reales de Compras"
            if any(v is None for v in precios.values())
            else None,
            "muestra_minima": self.muestra_minima,
            "fecha_corte": hasta.isoformat(),
        }

    def exportar(self, desde: date, hasta: date) -> bytes:
        movimientos = self.fuente.listar(desde, hasta)
        if self.datos_simulados or any(m.item_codigo.startswith("SIM-") for m in movimientos):
            raise ExportacionNoPermitida(
                "Los datos simulados no se pueden exportar como evidencia."
            )
        lineas = ["DATOS REALES — INFORME DE CONSUMO", "item,cantidad"]
        lineas.extend(f"{m.item_codigo},{m.consumo}" for m in self.metricas(desde, hasta))
        return ("\n".join(lineas) + "\n").encode()
