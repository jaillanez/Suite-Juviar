from __future__ import annotations

from ..domain.modelos import ExtraccionCV


class ExtraccionesEnMemoria:
    def __init__(self) -> None:
        self._datos: dict[str, ExtraccionCV] = {}

    def guardar_extraccion(self, extraccion: ExtraccionCV) -> None:
        self._datos[extraccion.id_original] = extraccion

    def obtener_extraccion(self, id_original: str) -> ExtraccionCV | None:
        return self._datos.get(id_original)

