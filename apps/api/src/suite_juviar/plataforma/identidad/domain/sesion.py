"""Sesión y permisos de la suite, independientes del autenticador concreto."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Sesion:
    actor: str
    empresa: str
    permisos: frozenset[str]
    identidad_simulada: bool
    # Sesión de quien sólo sube facturas con link + PIN: sólo pasa los permisos de esa pantalla
    # y sólo puede cargar en estas empresas.
    subida_pin: bool = False
    empresas: tuple[str, ...] = ()

    def puede(self, permiso: str) -> bool:
        return permiso in self.permisos
