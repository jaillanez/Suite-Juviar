"""CV que llegan por WhatsApp: entran a Selección por el mismo camino que los del mail de RRHH.

El teléfono desde el que lo mandaron queda como dato de contacto (sin verificar, como todo lo
que se extrae automáticamente).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ..domain.modelos import CampoExtraido, DocumentoEntrante, OrigenCV
from ..domain.puertos import RepositorioExtracciones
from .extraccion import ExtraerDatosCV
from .ingesta import IngestarCVs


class IncorporarCVWhatsapp:
    def __init__(self, ingestar: IngestarCVs, extraer: ExtraerDatosCV,
                 extracciones: RepositorioExtracciones) -> None:
        self._ingestar = ingestar
        self._extraer = extraer
        self._extracciones = extracciones

    def ejecutar(self, telefono: str, nombre_archivo: str, contenido: bytes, recibido_en: datetime,
                 referencia: str) -> bool:
        """True si entró; False si ese CV ya estaba (mismo archivo o mismo mensaje)."""
        documento = DocumentoEntrante(
            origen=OrigenCV.WHATSAPP,
            referencia_fuente=f"whatsapp:{referencia}",
            nombre_archivo=nombre_archivo,
            contenido=contenido,
            recibido_en=recibido_en,
            fuente_simulada=False,
        )
        incorporados = self._ingestar.ejecutar(_FuenteUnica(documento))
        for original in incorporados:
            self._sumar_contacto(self._extraer.ejecutar(original.id), telefono)
        return bool(incorporados)

    def _sumar_contacto(self, extraccion, telefono: str) -> None:
        if any(campo.nombre == "contacto" for campo in extraccion.campos):
            return
        contacto = CampoExtraido("contacto", f"+{telefono}", f"Recibido por WhatsApp desde +{telefono}")
        self._extracciones.guardar_extraccion(replace(
            extraccion,
            campos=(*extraccion.campos, contacto),
            campos_pendientes=tuple(c for c in extraccion.campos_pendientes if c != "contacto"),
        ))


class _FuenteUnica:
    estado = "WHATSAPP"

    def __init__(self, documento: DocumentoEntrante) -> None:
        self._documento = documento

    def listar_nuevos(self) -> list[DocumentoEntrante]:
        return [self._documento]
