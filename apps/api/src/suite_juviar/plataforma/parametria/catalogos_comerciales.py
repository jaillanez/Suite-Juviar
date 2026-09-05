"""Semilla de los catálogos que consume el sitio público.

Dueño del dato: Comercial / Exportación (§6.1, regla 6). Sistemas no los
edita. Cualquier alta o baja se hace acá y el worker la replica a la DMZ.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    tipo: str
    codigo: str
    nombre_es: str
    nombre_en: str
    orden: int


CATALOGOS: tuple[Item, ...] = (
    Item("linea_producto", "bulk_wine", "Vino a granel", "Bulk wine", 10),
    Item("linea_producto", "jcu_standard", "Mosto estándar", "Standard concentrate", 20),
    Item("linea_producto", "jcu_decolourised", "Mosto descolorido", "De-colored", 30),
    Item("linea_producto", "jcu_virgin", "Mosto virgen (sin SO₂)", "Virgin (no SO₂)", 40),
    Item("linea_producto", "jcu_alcoholised", "Alcoholizado", "Alcohol added", 50),

    Item("formato_despacho", "Flexitank_4650_gal", "Flexitank 4.650 gal", "Flexitank 4,650 gal", 10),
    Item("formato_despacho", "Flexitank_4200_gal", "Flexitank 4.200 gal", "Flexitank 4,200 gal", 20),
    Item("formato_despacho", "Wooden_bin_1560_kg", "Bin de madera 1.560 kg", "Wooden bin 1,560 kg", 30),
    Item("formato_despacho", "Drum_60_gal", "Tambor 60 gal", "Drum 60 gal", 40),

    Item("certificacion", "FSSC_22000", "FSSC 22000", "FSSC 22000", 10),
    Item("certificacion", "Organic_Letis", "Orgánico (Letis)", "Organic (Letis)", 20),
    Item("certificacion", "Kosher", "Kosher", "Kosher", 30),
    Item("certificacion", "Halal", "Halal", "Halal", 40),
    Item("certificacion", "Vegan", "Vegano", "Vegan", 50),
    Item("certificacion", "BDA_Sustainability", "BDA Sustentabilidad", "BDA Sustainability", 60),
    Item("certificacion", "SMETA_4P", "SMETA 4-Pillars", "SMETA 4-Pillars", 70),
    Item("certificacion", "Sellos_Argentinos", "Sellos Argentinos", "Sellos Argentinos", 80),
)
