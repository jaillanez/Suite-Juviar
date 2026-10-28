"""Normalización conservadora para buscar productores."""
from __future__ import annotations

import re
import unicodedata

LARGO_MINIMO = 2
MAXIMO_RESULTADOS = 20


def normalizar(texto: str | None) -> str:
    sin_tildes = unicodedata.normalize("NFKD", (texto or "").upper())
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9 ]+", " ", sin_tildes).strip()


def terminos(consulta: str | None) -> list[str]:
    palabras = [p for p in normalizar(consulta).split() if len(p) >= LARGO_MINIMO]
    return palabras[:5]
