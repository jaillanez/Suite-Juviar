"""Interpreta el período que pide el productor. Función pura.

El bot anterior aceptaba "marzo 2025", "este año", "últimos 6 meses" además
de los botones. Se mantiene: el productor ya está acostumbrado a escribirlo.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
# La vendimia va de diciembre a abril: la "cosecha 2026" arranca en diciembre
# de 2025. Sin esto, un camión de diciembre queda fuera de su propia cosecha.
MES_INICIO_COSECHA = 12
MAXIMO_ANIOS = 10


@dataclass(frozen=True)
class Periodo:
    desde: date
    hasta: date          # inclusive
    etiqueta: str

    def dias(self) -> int:
        return (self.hasta - self.desde).days + 1


def _normalizar(texto: str | None) -> str:
    limpio = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    return "".join(c for c in limpio if not unicodedata.combining(c))


def cosecha_de(dia: date) -> int:
    """Año de cosecha al que pertenece una fecha."""
    return dia.year + 1 if dia.month >= MES_INICIO_COSECHA else dia.year


def rango_cosecha(anio: int) -> Periodo:
    return Periodo(
        date(anio - 1, MES_INICIO_COSECHA, 1),
        date(anio, 11, 30),
        f"Cosecha {anio}",
    )


def _fin_de_mes(anio: int, mes: int) -> date:
    return date(anio + mes // 12, mes % 12 + 1, 1) - timedelta(days=1)


def interpretar(texto: str | None, hoy: date) -> Periodo | None:
    """None cuando no se entiende: el bot vuelve a ofrecer los botones."""
    t = _normalizar(texto)
    if not t:
        return None

    if "ultima cosecha" in t or t in {"1", "cosecha", "esta cosecha"}:
        return rango_cosecha(cosecha_de(hoy))

    if m := re.search(r"cosecha\s+(\d{4})", t):
        anio = int(m.group(1))
        if hoy.year - MAXIMO_ANIOS <= anio <= hoy.year + 1:
            return rango_cosecha(anio)
        return None

    if m := re.search(r"ultim[oa]s?\s+(\d{1,2})\s*(mes|meses|dia|dias|semana|semanas)", t):
        cantidad, unidad = int(m.group(1)), m.group(2)
        if cantidad < 1:
            return None
        dias = {"dia": 1, "dias": 1, "semana": 7, "semanas": 7}.get(unidad, 30) * cantidad
        if dias > 366 * MAXIMO_ANIOS:
            return None
        return Periodo(hoy - timedelta(days=dias - 1), hoy, f"Últimos {cantidad} {unidad}")

    if t in {"2", "ultimos 3 meses", "3 meses"}:
        return Periodo(hoy - timedelta(days=89), hoy, "Últimos 3 meses")

    if t in {"este ano", "ano", "este año"}:
        return Periodo(date(hoy.year, 1, 1), hoy, f"Año {hoy.year}")

    if t in {"hoy"}:
        return Periodo(hoy, hoy, "Hoy")

    if m := re.search(r"([a-z]+)\s+(\d{4})", t):
        mes = MESES.get(m.group(1))
        anio = int(m.group(2))
        if mes and hoy.year - MAXIMO_ANIOS <= anio <= hoy.year + 1:
            return Periodo(date(anio, mes, 1), _fin_de_mes(anio, mes),
                           f"{m.group(1).capitalize()} {anio}")

    if m := re.fullmatch(r"([a-z]+)", t):
        mes = MESES.get(m.group(1))
        if mes:
            anio = hoy.year if mes <= hoy.month else hoy.year - 1
            return Periodo(date(anio, mes, 1), _fin_de_mes(anio, mes),
                           f"{m.group(1).capitalize()} {anio}")

    if m := re.fullmatch(r"(\d{4})", t):
        anio = int(m.group(1))
        if hoy.year - MAXIMO_ANIOS <= anio <= hoy.year:
            return Periodo(date(anio, 1, 1), min(date(anio, 12, 31), hoy), f"Año {anio}")
    return None
