from __future__ import annotations

from ..domain.modelos import AnulacionAsistencia, Asistencia, Dictado, Tema


class CapacitacionEnMemoria:
    def __init__(self) -> None:
        self.temas: dict[str, Tema] = {}
        self.dictados: dict[str, Dictado] = {}
        self.asistencias: dict[tuple[str, str], Asistencia] = {}
        self.anulaciones: dict[tuple[str, str], AnulacionAsistencia] = {}

    def guardar_tema(self, tema: Tema) -> None:
        self.temas[tema.id] = tema

    def guardar_dictado(self, dictado: Dictado) -> None:
        if dictado.tema_id not in self.temas:
            raise ValueError("No existe el tema del dictado")
        self.dictados[dictado.id] = dictado

    def guardar_asistencia(self, asistencia: Asistencia) -> None:
        clave = (asistencia.dictado_id, asistencia.participante.legajo)
        if clave in self.asistencias:
            return
        self.asistencias[clave] = asistencia

    def anular_asistencia(self, anulacion: AnulacionAsistencia) -> None:
        clave = (anulacion.dictado_id, anulacion.legajo)
        if clave not in self.asistencias:
            raise ValueError("No existe la asistencia")
        self.anulaciones.setdefault(clave, anulacion)

    def obtener_anulacion(
        self,
        dictado_id: str,
        legajo: str,
    ) -> AnulacionAsistencia | None:
        return self.anulaciones.get((dictado_id, legajo))

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
            and (asistencia.dictado_id, asistencia.participante.legajo) not in self.anulaciones
        ]

    def todas_las_asistencias(self) -> list[Asistencia]:
        return [
            asistencia
            for asistencia in self.asistencias.values()
            if (asistencia.dictado_id, asistencia.participante.legajo) not in self.anulaciones
        ]
