"""Avisos de «datos de prueba» en pantallas y documentos.

En un servidor de demostración (SJ_OCULTAR_MARCAS_PRUEBA=si) los avisos no se
muestran, para que la presentación se vea como el sistema en uso. Los controles
siguen igual: con datos simulados nada arranca en producción.
"""

from __future__ import annotations

import os


def ocultar_marcas_prueba() -> bool:
    return os.getenv("SJ_OCULTAR_MARCAS_PRUEBA", "").strip().lower() in {"1", "true", "si", "sí"}


def marca_prueba(texto: str, simulado: bool = True) -> str | None:
    """El aviso a mostrar, o None si no corresponde o está oculto."""
    return texto if simulado and not ocultar_marcas_prueba() else None
