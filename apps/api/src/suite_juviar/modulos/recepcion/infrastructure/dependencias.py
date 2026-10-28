"""Wiring del módulo. Es el único lugar donde se eligen implementaciones."""

from __future__ import annotations

import os
from pathlib import Path

from suite_juviar.modulos.recepcion.application.casos_uso import AbrirRomaneo, CerrarRomaneo
from suite_juviar.modulos.recepcion.infrastructure.repositorio import RepositorioRomaneosSQL
from suite_juviar.plataforma.bitacora.infrastructure.repositorio import BitacoraSQL
from suite_juviar.plataforma.db.base import get_session
from suite_juviar.plataforma.outbox.infrastructure.repositorio import OutboxSQL

from .persistencia_local import AbrirRomaneoSQLite


async def abrir_romaneo():
    entorno = (os.getenv("SJ_ENTORNO") or os.getenv("ENTORNO") or "desarrollo").lower()
    if entorno == "prueba":
        ruta = os.getenv("SJ_RECEPCION_SQLITE_PATH") or str(
            Path(__file__).parents[5] / "datos" / "recepcion_demo.sqlite3"
        )
        yield AbrirRomaneoSQLite(ruta)
        return
    async for session in get_session():
        yield AbrirRomaneo(
            RepositorioRomaneosSQL(session), OutboxSQL(session), BitacoraSQL(session)
        )


async def cerrar_romaneo():
    async for session in get_session():
        yield CerrarRomaneo(
            RepositorioRomaneosSQL(session), OutboxSQL(session), BitacoraSQL(session)
        )
