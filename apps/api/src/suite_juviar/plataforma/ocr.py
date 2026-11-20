"""Lectura de texto de imágenes con tesseract, dentro del servidor.

La usan los módulos que leen papeles escaneados o fotografiados (certificados médicos,
facturas de proveedores). La imagen no sale del servidor: esta lectura no usa servicios
externos. Si tesseract no está instalado o falla, devuelve texto vacío.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def leer_texto_imagen(contenido: bytes, extension: str, *, idioma: str = "eng", timeout: int = 30) -> str:
    ruta = None
    try:
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as archivo:
            archivo.write(contenido)
            ruta = Path(archivo.name)
        proceso = subprocess.run(
            ["tesseract", str(ruta), "stdout", "-l", idioma, "--psm", "6"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        return proceso.stdout if proceso.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""
    finally:
        if ruta:
            ruta.unlink(missing_ok=True)
