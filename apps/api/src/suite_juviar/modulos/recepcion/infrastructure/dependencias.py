"""Wiring del módulo. Es el único lugar donde se eligen implementaciones."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from suite_juviar.modulos.recepcion.application.casos_uso import AbrirRomaneo, CerrarRomaneo
from suite_juviar.modulos.recepcion.infrastructure.repositorio import RepositorioRomaneosSQL
from suite_juviar.plataforma.bitacora.infrastructure.repositorio import BitacoraSQL
from suite_juviar.plataforma.db.base import get_session
from suite_juviar.plataforma.outbox.infrastructure.repositorio import OutboxSQL


def abrir_romaneo(session: Annotated[AsyncSession, Depends(get_session)]) -> AbrirRomaneo:
    return AbrirRomaneo(
        RepositorioRomaneosSQL(session), OutboxSQL(session), BitacoraSQL(session)
    )


def cerrar_romaneo(session: Annotated[AsyncSession, Depends(get_session)]) -> CerrarRomaneo:
    return CerrarRomaneo(
        RepositorioRomaneosSQL(session), OutboxSQL(session), BitacoraSQL(session)
    )
