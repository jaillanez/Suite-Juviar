"""Transporte intercambiable: Meta directo, Chattigo o salida durable simulada."""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Protocol
from uuid import uuid4

import psycopg

from .chattigo import ClienteChattigo, ConfigChattigo
from .conversacion import ZONA
from .meta_cloud import ClienteMeta, ConfigMeta


class Transporte(Protocol):
    def enviar_texto(self, telefono: str, texto: str) -> str: ...
    def enviar_imagen(self, telefono: str, url: str, epigrafe: str | None = None) -> str: ...
    def enviar_documento(
        self, telefono: str, url: str, nombre: str, epigrafe: str | None = None
    ) -> str: ...


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

    def descargar_media(self, media_id: str) -> tuple[bytes, str]:
        raise ErrorTransporte("en el simulador no se reciben fotos")

    def enviar_imagen(self, telefono: str, url: str, epigrafe: str | None = None) -> str:
        return self.enviar_texto(telefono, f"[IMAGEN] {epigrafe or ''}\n{url}".strip())

    def enviar_documento(
        self, telefono: str, url: str, nombre: str, epigrafe: str | None = None
    ) -> str:
        return self.enviar_texto(
            telefono, f"[DOCUMENTO] {nombre}\n{epigrafe or ''}\n{url}".strip()
        )


def modo() -> str:
    valor = os.environ.get("BOT_TRANSPORTE", "")
    if valor not in {"simulado", "chattigo", "meta"}:
        raise RuntimeError("BOT_TRANSPORTE tiene que ser 'simulado', 'chattigo' o 'meta'")
    return valor


def desde_entorno() -> Transporte:
    if modo() != "simulado" and os.environ.get("BOT_FECHA_SIMULADA"):
        raise RuntimeError(f"BOT_FECHA_SIMULADA no se admite con BOT_TRANSPORTE={modo()}")
    if modo() == "meta":
        return ClienteMeta(ConfigMeta.desde_entorno())
    if modo() == "chattigo":
        return ClienteChattigo(ConfigChattigo.desde_entorno())
    return TransporteSimulado(os.environ["BOT_DSN"])


def fecha_hoy() -> date:
    fijada = os.environ.get("BOT_FECHA_SIMULADA", "").strip()
    if fijada:
        if modo() != "simulado":
            raise RuntimeError("BOT_FECHA_SIMULADA sólo se admite en modo simulado")
        return date.fromisoformat(fijada)
    return datetime.now(ZONA).date()
