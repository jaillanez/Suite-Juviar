"""Repositorio de prueba; conserva el objeto original de forma inmutable."""

from __future__ import annotations

from ..domain.modelos import CVOriginal


class OriginalesEnMemoria:
    def __init__(self) -> None:
        self._por_id: dict[str, CVOriginal] = {}
        self._por_referencia: dict[str, str] = {}

    def guardar_original(self, original: CVOriginal) -> bool:
        if original.id in self._por_id or original.referencia_fuente in self._por_referencia:
            return False
        self._por_id[original.id] = original
        self._por_referencia[original.referencia_fuente] = original.id
        return True

    def obtener_original(self, id_original: str) -> CVOriginal | None:
        return self._por_id.get(id_original)

    def existe_referencia(self, referencia_fuente: str) -> bool:
        return referencia_fuente in self._por_referencia

