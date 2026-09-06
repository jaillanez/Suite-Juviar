"""Sesión asincrónica y convención de esquemas.

Cada módulo tiene su propio schema de PostgreSQL. Ningún módulo consulta las
tablas de otro: si necesita un dato ajeno, llega por evento y se guarda en su
propio modelo de lectura. El aislamiento se refuerza con permisos por schema.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from suite_juviar.config import settings

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


engine = create_async_engine(
    settings.database_url,          # rol de aplicación: sin DDL, sin DROP
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
