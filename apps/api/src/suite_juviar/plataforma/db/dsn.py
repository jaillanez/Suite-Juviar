"""Resolvedor único de la conexión PostgreSQL de la suite."""

from __future__ import annotations

import os
import warnings

VARIABLE = "SJ_DATABASE_URL"
HEREDADAS = (
    "RECEPCION_DSN_SUITE",
    "SJ_CONTACTOS_DSN",
    "SJ_RRHH_EPP_DATABASE_URL",
)
_DRIVER_ASINCRONICO = "postgresql+asyncpg://"
_PREFIJOS_PLANOS = ("postgresql://", "postgres://")


class FaltaLaBaseDeDatos(RuntimeError):
    pass


def _crudo() -> tuple[str, str] | None:
    valor = (os.getenv(VARIABLE) or "").strip()
    if valor:
        return valor, VARIABLE
    for heredada in HEREDADAS:
        valor = (os.getenv(heredada) or "").strip()
        if valor:
            warnings.warn(
                f"{heredada} quedó en desuso: cargá {VARIABLE} con la misma conexión.",
                DeprecationWarning,
                stacklevel=3,
            )
            return valor, heredada
    return None


def hay_base() -> bool:
    return _crudo() is not None


def _resolver(obligatorio: bool) -> str | None:
    encontrado = _crudo()
    if encontrado is None:
        if obligatorio:
            raise FaltaLaBaseDeDatos(
                f"Falta {VARIABLE}. No hay valor por omisión para evitar escribir en otra base."
            )
        return None
    return encontrado[0]


def dsn_psycopg(obligatorio: bool = True) -> str:
    valor = _resolver(obligatorio)
    if valor is None:
        return ""
    if valor.startswith(_DRIVER_ASINCRONICO):
        return "postgresql://" + valor[len(_DRIVER_ASINCRONICO):]
    if valor.startswith(_PREFIJOS_PLANOS):
        return valor
    raise FaltaLaBaseDeDatos(
        f"{VARIABLE} debe comenzar con postgresql:// o {_DRIVER_ASINCRONICO}."
    )


def url_sqlalchemy(obligatorio: bool = True) -> str:
    valor = _resolver(obligatorio)
    if valor is None:
        return ""
    if valor.startswith(_DRIVER_ASINCRONICO):
        return valor
    for prefijo in _PREFIJOS_PLANOS:
        if valor.startswith(prefijo):
            return _DRIVER_ASINCRONICO + valor[len(prefijo):]
    raise FaltaLaBaseDeDatos(
        f"{VARIABLE} debe comenzar con postgresql:// o {_DRIVER_ASINCRONICO}."
    )
