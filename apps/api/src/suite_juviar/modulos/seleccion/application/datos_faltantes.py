"""Datos que todo CV debería traer y muchas veces no trae, por la falta de un formato único."""

from __future__ import annotations

from collections.abc import Iterable

from .datos_cv import valores_de_ficha

# Lo que pide RRHH: edad o fecha de nacimiento, nivel de estudios y experiencia laboral.
OBLIGATORIOS = ("edad_o_fecha_nacimiento", "nivel_estudios", "experiencia")


def datos_faltantes(campos_leidos: Iterable[str], ficha_ia: dict[str, object] | None = None) -> list[str]:
    """Obligatorios que no encontró ninguna de las dos lecturas: ni las reglas ni la IA."""
    leidos = set(campos_leidos) | set(valores_de_ficha(ficha_ia))
    return [c for c in OBLIGATORIOS if c not in leidos]
