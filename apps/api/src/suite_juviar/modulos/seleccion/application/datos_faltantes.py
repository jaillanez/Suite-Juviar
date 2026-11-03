"""Datos que todo CV debería traer y muchas veces no trae, por la falta de un formato único."""

from __future__ import annotations

from collections.abc import Iterable

# Lo que pide RRHH: edad o fecha de nacimiento, nivel de estudios y experiencia laboral.
OBLIGATORIOS = ("edad_o_fecha_nacimiento", "nivel_estudios", "experiencia")

# Dónde está cada dato en la ficha que arma la IA, si el CV ya se leyó con IA.
_EN_FICHA_IA = {"edad_o_fecha_nacimiento": "edad", "nivel_estudios": "estudios", "experiencia": "experiencia"}


def datos_faltantes(campos_leidos: Iterable[str], ficha_ia: dict[str, object] | None = None) -> list[str]:
    """Obligatorios que no aparecen ni en la lectura automática ni en la ficha de la IA."""
    leidos = set(campos_leidos)
    ficha_ia = ficha_ia or {}
    return [c for c in OBLIGATORIOS if c not in leidos and not ficha_ia.get(_EN_FICHA_IA[c])]
