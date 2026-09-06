from __future__ import annotations

from ..domain.modelos_mvp import DocumentoConstancia
from ..domain.puertos_mvp import GeneradorConstancia, RepositorioConstancias, RepositorioEntregas


class ObtenerConstanciaPDF:
    def __init__(
        self,
        entregas: RepositorioEntregas,
        constancias: RepositorioConstancias,
        generador: GeneradorConstancia,
    ) -> None:
        self._entregas = entregas
        self._constancias = constancias
        self._generador = generador

    def ejecutar(self, id_entrega: str) -> DocumentoConstancia | None:
        original = self._constancias.obtener(id_entrega)
        if original is not None:
            return original
        entrega = self._entregas.obtener(id_entrega)
        if entrega is None:
            return None
        original = self._generador.generar(entrega)
        self._constancias.guardar_original(original)
        return self._constancias.obtener(id_entrega)
