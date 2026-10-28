"""Extracción explicable: ningún dato automático nace verificado."""

from __future__ import annotations

from datetime import UTC, datetime

from ..domain.modelos import ExtraccionCV
from ..domain.puertos import (
    ExtractorCampos,
    ExtractorTexto,
    RepositorioCVOriginales,
    RepositorioExtracciones,
)

CAMPOS_REQUERIDOS = (
    "edad_o_fecha_nacimiento",
    "nivel_estudios",
    "experiencia",
    "oficio",
    "localidad",
    "contacto",
)


class ExtraerDatosCV:
    def __init__(
        self,
        originales: RepositorioCVOriginales,
        extracciones: RepositorioExtracciones,
        texto: ExtractorTexto,
        campos: ExtractorCampos,
    ) -> None:
        self._originales = originales
        self._extracciones = extracciones
        self._texto = texto
        self._campos = campos

    def ejecutar(self, id_original: str) -> ExtraccionCV:
        original = self._originales.obtener_original(id_original)
        if original is None:
            raise ValueError("No existe el CV original solicitado")
        texto = self._texto.extraer_texto(original.contenido)
        campos = self._campos.extraer_campos(texto) if texto.strip() else []
        presentes = {campo.nombre for campo in campos}
        extraccion = ExtraccionCV(
            id_original=id_original,
            campos=tuple(campos),
            campos_pendientes=tuple(campo for campo in CAMPOS_REQUERIDOS if campo not in presentes),
            extraido_en=datetime.now(UTC),
        )
        self._extracciones.guardar_extraccion(extraccion)
        return extraccion

