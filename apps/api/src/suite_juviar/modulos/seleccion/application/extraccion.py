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
SIN_TEXTO = "SIN_TEXTO"


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

    def ejecutar(self, id_original: str, *, conservar_anteriores: bool = False) -> ExtraccionCV:
        """Lee el CV con las reglas. Al volver a leer, lo que ya estaba y la nueva lectura no encontró
        (por ejemplo, el teléfono del WhatsApp) se conserva."""
        original = self._originales.obtener_original(id_original)
        if original is None:
            raise ValueError("No existe el CV original solicitado")
        texto = self._texto.extraer_texto(original.contenido)
        campos = self._campos.extraer_campos(texto) if texto.strip() else []
        anterior = self._extracciones.obtener_extraccion(id_original) if conservar_anteriores else None
        if anterior is not None:
            nuevos = {campo.nombre for campo in campos}
            campos = [*campos, *(campo for campo in anterior.campos if campo.nombre not in nuevos)]
        presentes = {campo.nombre for campo in campos}
        extraccion = ExtraccionCV(
            id_original=id_original,
            campos=tuple(campos),
            campos_pendientes=tuple(campo for campo in CAMPOS_REQUERIDOS if campo not in presentes),
            extraido_en=datetime.now(UTC),
            # Sin texto (OCR vacío, archivo dañado): lo que falta no se pudo leer, no es que el CV no lo traiga.
            estado="NO_VERIFICADO" if texto.strip() else SIN_TEXTO,
        )
        self._extracciones.guardar_extraccion(extraccion)
        return extraccion

