from __future__ import annotations

from dataclasses import replace

from ..domain.modelos import (
    FIRMADA_EN_PAPEL,
    AnulacionAsistencia,
    Asistencia,
    Dictado,
    PlanillaEscaneada,
    Tema,
)


class CapacitacionEnMemoria:
    def __init__(self) -> None:
        self.temas: dict[str, Tema] = {}
        self.dictados: dict[str, Dictado] = {}
        self.asistencias: dict[tuple[str, str], Asistencia] = {}
        self.anulaciones: dict[tuple[str, str], AnulacionAsistencia] = {}
        self.planillas: dict[str, PlanillaEscaneada] = {}
        # La imagen va aparte para que listar la bandeja no cargue todos los archivos.
        self.archivos_planillas: dict[str, bytes] = {}

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

    def asistencias_del_dictado_con_anuladas(
        self, dictado_id: str
    ) -> list[tuple[Asistencia, AnulacionAsistencia | None]]:
        return [
            (asistencia, self.anulaciones.get((dictado_id, asistencia.participante.legajo)))
            for asistencia in self.asistencias.values()
            if asistencia.dictado_id == dictado_id
        ]

    def todas_las_asistencias(self) -> list[Asistencia]:
        return [
            asistencia
            for asistencia in self.asistencias.values()
            if (asistencia.dictado_id, asistencia.participante.legajo) not in self.anulaciones
        ]

    def guardar_planilla(self, planilla: PlanillaEscaneada) -> None:
        self.planillas[planilla.id] = planilla

    def guardar_archivo_planilla(self, planilla_id: str, contenido: bytes) -> None:
        self.archivos_planillas[planilla_id] = contenido

    def archivo_planilla(self, planilla_id: str) -> bytes | None:
        return self.archivos_planillas.get(planilla_id)

    def obtener_planilla(self, planilla_id: str) -> PlanillaEscaneada | None:
        return self.planillas.get(planilla_id)

    def listar_planillas(self) -> list[PlanillaEscaneada]:
        return sorted(self.planillas.values(), key=lambda p: p.cargada_en, reverse=True)

    def confirmar_firma_papel(self, dictado_id: str, legajo: str) -> None:
        """La firma que estaba pendiente en papel quedó respaldada por la planilla escaneada."""
        clave = (dictado_id, legajo)
        asistencia = self.asistencias.get(clave)
        if asistencia is None or asistencia.estado_firma != "PENDIENTE_FIRMA_PAPEL":
            raise ValueError("La asistencia no está pendiente de firma en papel")
        self.asistencias[clave] = replace(asistencia, estado_firma=FIRMADA_EN_PAPEL)
