"""Ingesta que conserva bytes originales y sólo agrega una capa de registro."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from ..domain.modelos import CVOriginal
from ..domain.puertos import FuenteCV, RepositorioCVOriginales


class IngestarCVs:
    def __init__(self, originales: RepositorioCVOriginales) -> None:
        self._originales = originales

    def ejecutar(self, fuente: FuenteCV) -> list[CVOriginal]:
        incorporados: list[CVOriginal] = []
        for entrante in fuente.listar_nuevos():
            if self._originales.existe_referencia(entrante.referencia_fuente):
                continue
            digest = hashlib.sha256(entrante.contenido).hexdigest()
            original = CVOriginal(
                id=digest,
                origen=entrante.origen,
                referencia_fuente=entrante.referencia_fuente,
                nombre_archivo=entrante.nombre_archivo,
                contenido=entrante.contenido,
                sha256=digest,
                recibido_en=entrante.recibido_en,
                incorporado_en=datetime.now(UTC),
                fuente_simulada=entrante.fuente_simulada,
            )
            if self._originales.guardar_original(original):
                incorporados.append(original)
        return incorporados

