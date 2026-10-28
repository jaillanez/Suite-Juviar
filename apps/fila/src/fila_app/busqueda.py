"""Normalización de consultas del buscador de productores."""
from __future__ import annotations

import re
import unicodedata


def normalizar(texto: str | None) -> str:
    valor = unicodedata.normalize("NFKD", (texto or "").upper())
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9 ]+", " ", valor).strip()


def terminos(consulta: str | None) -> list[str]:
    return [p for p in normalizar(consulta).split() if len(p) >= 2][:5]
