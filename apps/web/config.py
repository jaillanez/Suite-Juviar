"""Configuración de apps/web. Todo por variable de entorno; nada hardcodeado."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    dsn_dmz: str
    origen_permitido: str
    limite_por_hora: int
    entorno: str

    @classmethod
    def desde_entorno(cls) -> Config:
        dsn = os.environ.get("WEB_DSN_DMZ")
        if not dsn:
            raise RuntimeError(
                "Falta WEB_DSN_DMZ. apps/web sólo se conecta a la base de la DMZ; "
                "si esta variable apunta al servidor interno, la instalación está mal."
            )
        return cls(
            dsn_dmz=dsn,
            origen_permitido=os.environ.get("WEB_ORIGEN", "https://www.juviar.com.ar"),
            limite_por_hora=int(os.environ.get("WEB_LIMITE_HORA", "30")),
            entorno=os.environ.get("WEB_ENTORNO", "produccion"),
        )
