"""Configuración del worker de recepción, exclusivamente por entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Sede:
    codigo: str
    host: str
    puerto: int
    servicio: str


@dataclass(frozen=True)
class Config:
    sedes: tuple[Sede, ...]
    usuario: str
    clave: str
    dsn_suite: str
    dsn_dmz: str
    ventana_dias: int
    ventana_nocturna_dias: int
    minimo_filas: int
    tope_ausencias: float

    @classmethod
    def desde_entorno(cls) -> Config:
        def requerida(nombre: str) -> str:
            valor = os.environ.get(nombre, "").strip()
            if not valor:
                raise RuntimeError(f"Falta la variable de entorno {nombre}")
            return valor

        activas = tuple(
            codigo.strip()
            for codigo in requerida("RECEPCION_SEDES_ACTIVAS").split(",")
            if codigo.strip()
        )
        sedes = tuple(
            Sede(
                codigo=codigo,
                host=requerida(f"RECEPCION_{codigo.upper()}_HOST"),
                puerto=int(os.environ.get(f"RECEPCION_{codigo.upper()}_PUERTO", "1521")),
                servicio=os.environ.get(f"RECEPCION_{codigo.upper()}_SERVICIO", "nexus"),
            )
            for codigo in activas
        )
        return cls(
            sedes=sedes,
            usuario=requerida("RECEPCION_ORACLE_USUARIO"),
            clave=requerida("RECEPCION_ORACLE_CLAVE"),
            dsn_suite=requerida("RECEPCION_DSN_SUITE"),
            dsn_dmz=requerida("RECEPCION_DSN_DMZ"),
            ventana_dias=int(os.environ.get("RECEPCION_VENTANA_DIAS", "15")),
            ventana_nocturna_dias=int(os.environ.get("RECEPCION_VENTANA_NOCTURNA_DIAS", "200")),
            minimo_filas=int(os.environ.get("RECEPCION_MINIMO_FILAS", "1")),
            tope_ausencias=float(os.environ.get("RECEPCION_TOPE_AUSENCIAS", "0.2")),
        )
