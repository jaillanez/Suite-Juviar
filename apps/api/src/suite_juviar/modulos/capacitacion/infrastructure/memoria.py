from __future__ import annotations

from ..domain.modelos import Asistencia, Dictado, Tema


class CapacitacionEnMemoria:
    def __init__(self) -> None:
        self.temas: dict[str, Tema] = {}
        self.dictados: dict[str, Dictado] = {}
        self.asistencias: dict[tuple[str, str], Asistencia] = {}

    def guardar_tema(self, tema: Tema) -> None:
        self.temas[tema.id] = tema

    def guardar_dictado(self, dictado: Dictado) -> None:
        if dictado.tema_id not in self.temas:
            raise ValueError("No existe el tema del dictado")
        self.dictados[dictado.id] = dictado

    def guardar_asistencia(self, asistencia: Asistencia) -> None:
        self.asistencias[(asistencia.dictado_id, asistencia.participante.legajo)] = asistencia

    def obtener_tema(self, tema_id: str) -> Tema | None:
        return self.temas.get(tema_id)

    def obtener_dictado(self, dictado_id: str) -> Dictado | None:
        return self.dictados.get(dictado_id)

    def dictados_del_tema(self, tema_id: str) -> list[Dictado]:
        return [dictado for dictado in self.dictados.values() if dictado.tema_id == tema_id]

    def asistencias_del_dictado(self, dictado_id: str) -> list[Asistencia]:
        return [
            asistencia
            for asistencia in self.asistencias.values()
            if asistencia.dictado_id == dictado_id
        ]

    def todas_las_asistencias(self) -> list[Asistencia]:
        return list(self.asistencias.values())


class ConfiguracionSimulada:
    estado = "PROPUESTA_SIN_VALIDAR"
    dueno_dato = "RRHH"
    umbral_supervisor = 80.0

