"""Sesión asincrónica y convención de esquemas.

Cada módulo tiene su propio schema de PostgreSQL. Ningún módulo consulta las
tablas de otro: si necesita un dato ajeno, llega por evento y se guarda en su
propio modelo de lectura. El aislamiento se refuerza con permisos por schema.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from . import dsn as _dsn

ESQUEMAS = (
    "plataforma",
    "bitacora",
    "turnos",
    "rrhh_epp",
    "seleccion",
    "capacitacion",
    "cosecha",
    "recepcion",
    "ddjj",
    "lectura",  # modelos de lectura que alimentan al bot en la DMZ
)


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=1)
def obtener_motor() -> AsyncEngine:
    return create_async_engine(_dsn.url_sqlalchemy(), pool_pre_ping=True, echo=False)


@lru_cache(maxsize=1)
def obtener_fabrica_de_sesiones() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(obtener_motor(), expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with obtener_fabrica_de_sesiones()() as session:
        yield session


def reiniciar_motor() -> None:
    """Olvida motor y fábrica; reservado para pruebas de configuración."""
    obtener_fabrica_de_sesiones.cache_clear()
    obtener_motor.cache_clear()
