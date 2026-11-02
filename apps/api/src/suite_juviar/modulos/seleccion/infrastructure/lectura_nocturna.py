"""Lectura diaria de las casillas de RRHH dentro del mismo proceso de la API.

Corre en la API porque los CV viven en su base local; un proceso aparte no la ve.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..application.correo import CorreoRRHH

_registro = logging.getLogger(__name__)
ZONA = ZoneInfo("America/Argentina/San_Juan")


def segundos_hasta(hora: int, ahora: datetime) -> float:
    proxima = ahora.replace(hour=hora, minute=0, second=0, microsecond=0)
    if proxima <= ahora:
        proxima += timedelta(days=1)
    return (proxima - ahora).total_seconds()


def iniciar(correo: CorreoRRHH, hora: int) -> threading.Thread:
    def ciclo() -> None:
        while True:
            threading.Event().wait(segundos_hasta(hora, datetime.now(ZONA)))
            for resultado in correo.leer_todas():
                if resultado.error:
                    _registro.warning("Correo RRHH %s: %s", resultado.empresa, resultado.error)
                else:
                    _registro.info("Correo RRHH %s: %s CV nuevos de %s adjuntos",
                                   resultado.empresa, resultado.incorporados, resultado.adjuntos)
                if resultado.incompleta or resultado.salteados:
                    _registro.warning("Correo RRHH %s: lectura incompleta=%s, %s correos salteados",
                                      resultado.empresa, resultado.incompleta, resultado.salteados)

    hilo = threading.Thread(target=ciclo, name="lectura-correo-rrhh", daemon=True)
    hilo.start()
    return hilo
