"""Sesión y permisos de la suite, independientes del autenticador concreto."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Sesion:
    actor: str
    empresa: str
    permisos: frozenset[str]
    identidad_simulada: bool

    def puede(self, permiso: str) -> bool:
        return permiso in self.permisos
