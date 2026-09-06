from __future__ import annotations

from ..domain.modelos_mvp import DocumentoConstancia, SolicitudConstancia
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
        historial = list(reversed(self._entregas.listar_por_legajo(entrega.legajo.legajo)))
        posicion = next(
            (indice for indice, registrada in enumerate(historial) if registrada.id == id_entrega),
            None,
        )
        if posicion is None:
            return None
        incluidas = tuple(historial[: posicion + 1])
        anterior = self.ejecutar(incluidas[-2].id) if len(incluidas) > 1 else None
        original = self._generador.generar(
            SolicitudConstancia(
                entrega_actual=entrega,
                entregas_incluidas=incluidas,
                version=(anterior.version + 1) if anterior else 1,
                anula_a=anterior.id_entrega if anterior else None,
            )
        )
        self._constancias.guardar_original(original)
        return self._constancias.obtener(id_entrega)
