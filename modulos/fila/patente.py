"""Normalización de patentes argentinas."""
from __future__ import annotations

import re

_VIEJA = re.compile(r"^[A-Z]{3}\d{3}$")
_MERCOSUR = re.compile(r"^[A-Z]{2}\d{3}[A-Z]{2}$")


class PatenteInvalida(ValueError):
    pass


def normalizar(texto: str | None) -> str:
    patente = re.sub(r"[^A-Za-z0-9]", "", texto or "").upper()
    if not (_VIEJA.match(patente) or _MERCOSUR.match(patente)):
        raise PatenteInvalida("la patente tiene que ser AAA123 o AA123BB")
    return patente
