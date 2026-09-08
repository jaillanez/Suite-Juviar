from __future__ import annotations

from ..domain.modelos import ConfirmacionCampo, ConsultaOriginal, ExtraccionCV


class ExtraccionesEnMemoria:
    def __init__(self) -> None:
        self._datos: dict[str, ExtraccionCV] = {}
        self._confirmaciones: dict[tuple[str, str], ConfirmacionCampo] = {}
        self._consultas: list[ConsultaOriginal] = []

    def guardar_extraccion(self, extraccion: ExtraccionCV) -> None:
        self._datos[extraccion.id_original] = extraccion

    def obtener_extraccion(self, id_original: str) -> ExtraccionCV | None:
        return self._datos.get(id_original)

    def listar_extracciones(self) -> list[ExtraccionCV]:
        return list(self._datos.values())

    def confirmar(self, confirmacion: ConfirmacionCampo) -> None:
        self._confirmaciones[(confirmacion.id_original, confirmacion.campo)] = confirmacion

    def confirmaciones(self, id_original: str) -> list[ConfirmacionCampo]:
        return [valor for (cv, _), valor in self._confirmaciones.items() if cv == id_original]

    def auditar_original(self, consulta: ConsultaOriginal) -> None:
        self._consultas.append(consulta)

    def consultas_original(self, id_original: str) -> list[ConsultaOriginal]:
        return [consulta for consulta in self._consultas if consulta.id_original == id_original]
