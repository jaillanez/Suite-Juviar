"""Adaptadores de entrada sin supuestos sobre rutas ni credenciales corporativas."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ..domain.modelos import DocumentoEntrante, OrigenCV


class CarpetaServidorCV:
    estado = "CONFIGURABLE_RUTA_REAL_PENDIENTE"

    def __init__(self, ruta: str | Path) -> None:
        self._ruta = Path(ruta)

    def listar_nuevos(self) -> list[DocumentoEntrante]:
        if not self._ruta.is_dir():
            return []
        return [
            DocumentoEntrante(
                origen=OrigenCV.CARPETA_CHIMBAS,
                referencia_fuente=f"archivo:{archivo.resolve()}",
                nombre_archivo=archivo.name,
                contenido=archivo.read_bytes(),
                recibido_en=datetime.fromtimestamp(archivo.stat().st_mtime, tz=UTC),
                fuente_simulada=False,
            )
            for archivo in sorted(self._ruta.glob("*.pdf"))
            if archivo.is_file()
        ]


class BandejaCorreoLocalSimulada:
    estado = "SIMULADO_SIN_CREDENCIALES_DE_CORREO"

    def __init__(self, ruta_adjuntos: str | Path) -> None:
        self._ruta = Path(ruta_adjuntos)

    def listar_nuevos(self) -> list[DocumentoEntrante]:
        if not self._ruta.is_dir():
            return []
        return [
            DocumentoEntrante(
                origen=OrigenCV.CORREO,
                referencia_fuente=f"correo-simulado:{archivo.name}",
                nombre_archivo=archivo.name,
                contenido=archivo.read_bytes(),
                recibido_en=datetime.fromtimestamp(archivo.stat().st_mtime, tz=UTC),
                fuente_simulada=True,
            )
            for archivo in sorted(self._ruta.glob("*.pdf"))
            if archivo.is_file()
        ]

