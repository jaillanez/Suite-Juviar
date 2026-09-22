"""Transporte intercambiable: Chattigo real o salida durable simulada."""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Protocol
from uuid import uuid4

import psycopg

from .chattigo import ClienteChattigo, ConfigChattigo
from .conversacion import ZONA


class Transporte(Protocol):
    def enviar_texto(self, telefono: str, texto: str) -> str: ...


class ErrorTransporte(RuntimeError):
    pass


class TransporteSimulado:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def enviar_texto(self, telefono: str, texto: str) -> str:
        wamid = f"sim.out.{uuid4().hex}"
        try:
            with psycopg.connect(self._dsn) as conexion:
                conexion.execute(
                    """INSERT INTO consulta.bot_salida_simulada
                           (telefono, texto, wamid_salida) VALUES (%s, %s, %s)""",
                    (telefono, texto, wamid),
                )
        except psycopg.Error as exc:
            raise ErrorTransporte(f"salida simulada: {exc.__class__.__name__}") from exc
        return wamid


def modo() -> str:
    valor = os.environ.get("BOT_TRANSPORTE", "")
    if valor not in {"simulado", "chattigo"}:
        raise RuntimeError("BOT_TRANSPORTE tiene que ser 'simulado' o 'chattigo'")
    return valor


def desde_entorno() -> Transporte:
    if modo() == "chattigo":
        if os.environ.get("BOT_FECHA_SIMULADA"):
            raise RuntimeError("BOT_FECHA_SIMULADA no se admite con BOT_TRANSPORTE=chattigo")
        return ClienteChattigo(ConfigChattigo.desde_entorno())
    return TransporteSimulado(os.environ["BOT_DSN"])


def fecha_hoy() -> date:
    fijada = os.environ.get("BOT_FECHA_SIMULADA", "").strip()
    if fijada:
        if modo() != "simulado":
            raise RuntimeError("BOT_FECHA_SIMULADA sólo se admite en modo simulado")
        return date.fromisoformat(fijada)
    return datetime.now(ZONA).date()
