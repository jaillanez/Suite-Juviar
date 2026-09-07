from __future__ import annotations

from uuid import uuid4

from ..domain.modelos import Adjunto
from ..domain.puertos import FuenteLegajos, RepositorioAdjuntos


class GestionarLegajo:
    def __init__(self, legajos: FuenteLegajos, adjuntos: RepositorioAdjuntos):
        self.legajos = legajos
        self.adjuntos = adjuntos

    def ficha(self, legajo: str) -> dict[str, str] | None:
        persona = self.legajos.obtener(legajo)
        if persona is None:
            return None
        formato = "FICHA_ENAV" if persona.empresa.upper() == "ENAV" else "FICHA_JUBIAR"
        return {
            "legajo": persona.legajo,
            "nombre_completo": persona.nombre_completo,
            "empresa": persona.empresa,
            "sector": persona.sector,
            "puesto": persona.puesto,
            "formato": formato,
        }

    def adjuntar(self, legajo: str, nombre: str, contenido: bytes) -> Adjunto:
        if self.legajos.obtener(legajo) is None:
            raise LookupError("El legajo no existe en la fuente maestra.")
        adjunto = Adjunto(str(uuid4()), legajo, nombre, bytes(contenido))
        self.adjuntos.guardar(adjunto)
        return adjunto
