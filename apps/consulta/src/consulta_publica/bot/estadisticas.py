"""Cálculo de las estadísticas del productor. Función pura.

El azúcar se promedia PESADO POR KILOS, no por entrega: un camión de 12.000 kg
pesa más en el promedio que uno de 3.000. El bot anterior promediaba simple, y
por eso el número no coincidía con lo que paga la bodega.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

MAXIMO_VARIEDADES = 3   # el resto se agrupa en "Otras"


@dataclass(frozen=True)
class Entrega:
    fecha: date
    ciu: str
    variedad: str
    neto: int
    azucar: Decimal | float | None
    sede: str = ""


@dataclass
class Resumen:
    total_kg: int = 0
    entregas: int = 0
    por_variedad: list[tuple[str, int]] = field(default_factory=list)
    por_dia: list[tuple[date, int]] = field(default_factory=list)
    azucar_promedio: float | None = None
    azucar_min: float | None = None
    azucar_max: float | None = None
    primera: date | None = None
    ultima: date | None = None

    @property
    def promedio_por_entrega(self) -> int:
        return round(self.total_kg / self.entregas) if self.entregas else 0


def resumir(entregas: list[Entrega]) -> Resumen:
    r = Resumen()
    if not entregas:
        return r

    kg_variedad: dict[str, int] = defaultdict(int)
    kg_dia: dict[date, int] = defaultdict(int)
    azucares: list[tuple[float, int]] = []

    for e in entregas:
        neto = int(e.neto or 0)
        if neto <= 0:
            continue
        r.total_kg += neto
        r.entregas += 1
        kg_variedad[(e.variedad or "Sin variedad").strip()] += neto
        kg_dia[e.fecha] += neto
        if e.azucar is not None:
            azucares.append((float(e.azucar), neto))

    if not r.entregas:
        return r

    ordenadas = sorted(kg_variedad.items(), key=lambda kv: -kv[1])
    if len(ordenadas) > MAXIMO_VARIEDADES:
        otras = sum(kg for _, kg in ordenadas[MAXIMO_VARIEDADES:])
        ordenadas = ordenadas[:MAXIMO_VARIEDADES] + [("Otras", otras)]
    r.por_variedad = ordenadas
    r.por_dia = sorted(kg_dia.items())
    r.primera, r.ultima = r.por_dia[0][0], r.por_dia[-1][0]

    if azucares:
        kilos = sum(k for _, k in azucares)
        r.azucar_promedio = round(sum(a * k for a, k in azucares) / kilos, 1)
        r.azucar_min = min(a for a, _ in azucares)
        r.azucar_max = max(a for a, _ in azucares)
    return r


def formatear_kg(valor: int | None) -> str:
    return f"{valor or 0:,}".replace(",", ".") + " kg"
