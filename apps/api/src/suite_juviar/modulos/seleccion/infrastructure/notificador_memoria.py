from __future__ import annotations

from ..domain.modelos import AvisoCoincidencia


class NotificadorEnMemoria:
    estado = "SIMULADO_SIN_CANAL_CORPORATIVO"

    def __init__(self) -> None:
        self.avisos: list[AvisoCoincidencia] = []

    def avisar(self, aviso: AvisoCoincidencia) -> None:
        self.avisos.append(aviso)

