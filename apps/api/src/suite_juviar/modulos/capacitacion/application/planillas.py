"""Planillas de asistencia firmadas a mano: se escanean, quedan en bandeja y RRHH las aprueba."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from ..domain.modelos import (
    FIRMADA_EN_PAPEL,
    Asistencia,
    FilaPlanilla,
    Participante,
    PlanillaEscaneada,
)
from ..domain.puertos import LectorPlanillas, RepositorioCapacitacion, RepositorioPlanillas

TAMANO_MAXIMO = 10 * 1024 * 1024
EXTENSIONES = (".pdf", ".jpg", ".jpeg", ".png", ".webp")


class PlanillasEscaneadas:
    def __init__(self, repositorio: RepositorioCapacitacion, planillas: RepositorioPlanillas,
                 lector: LectorPlanillas) -> None:
        self._repositorio = repositorio
        self._planillas = planillas
        self._lector = lector
        self._candado = RLock()

    def cargar(self, dictado_id: str, nombre: str, contenido: bytes, actor: str,
               esperados: list[FilaPlanilla]) -> PlanillaEscaneada:
        if self._repositorio.obtener_dictado(dictado_id) is None:
            raise LookupError("No existe el dictado")
        if not nombre.lower().endswith(EXTENSIONES):
            raise ValueError("La planilla tiene que ser una foto (JPG, PNG o WEBP) o un PDF.")
        if not contenido:
            raise ValueError("El archivo está vacío.")
        if len(contenido) > TAMANO_MAXIMO:
            raise ValueError("El archivo supera los 10 MB.")
        filas, motor, mensaje = self._lector.leer(nombre, contenido, esperados)
        planilla = PlanillaEscaneada(
            id=str(uuid4()), dictado_id=dictado_id, nombre_archivo=nombre,
            cargada_en=datetime.now(UTC), cargada_por=actor, filas=tuple(filas),
            motor=motor, mensaje=mensaje,
        )
        self._planillas.guardar_archivo_planilla(planilla.id, contenido)
        self._planillas.guardar_planilla(planilla)
        return planilla

    def aprobar(self, planilla_id: str, filas: list[FilaPlanilla], actor: str) -> PlanillaEscaneada:
        with self._candado:
            planilla = self._pendiente(planilla_id)
            legajos = [f.legajo.strip() for f in filas]
            if any(not legajo for legajo in legajos):
                raise ValueError("Cada fila necesita el legajo.")
            if len(set(legajos)) != len(legajos):
                raise ValueError("Hay un legajo repetido en la planilla.")
            if any(f.presente is None for f in filas):
                raise ValueError("Marcá presente o ausente en todas las filas antes de aprobar.")
            if any(not f.nombre_completo.strip() for f in filas):
                raise ValueError("Cada fila necesita el apellido y nombre.")
            existentes = {a.participante.legajo: a for a, _ in
                          self._repositorio.asistencias_del_dictado_con_anuladas(planilla.dictado_id)}
            resultado = {"presentes": 0, "ausentes": 0, "firmas_confirmadas": 0, "sin_cambios": []}
            for fila in filas:
                legajo = fila.legajo.strip()
                previa = existentes.get(legajo)
                if previa is None:
                    self._repositorio.guardar_asistencia(Asistencia(
                        planilla.dictado_id,
                        Participante(legajo, fila.nombre_completo.strip()),
                        bool(fila.presente), None,
                        FIRMADA_EN_PAPEL if fila.presente else "AUSENTE",
                    ))
                    resultado["presentes" if fila.presente else "ausentes"] += 1
                elif fila.presente and previa.presente and previa.estado_firma == "PENDIENTE_FIRMA_PAPEL" \
                        and self._repositorio.obtener_anulacion(planilla.dictado_id, legajo) is None:
                    self._planillas.confirmar_firma_papel(planilla.dictado_id, legajo)
                    resultado["firmas_confirmadas"] += 1
                else:
                    # Ya estaba registrado (por tablet, anulado o con otro estado): no se pisa.
                    resultado["sin_cambios"].append(legajo)
            aprobada = replace(planilla, filas=tuple(filas), estado="APROBADA", revisada_por=actor,
                               revisada_en=datetime.now(UTC), resultado=resultado)
            self._planillas.guardar_planilla(aprobada)
            return aprobada

    def descartar(self, planilla_id: str, motivo: str, actor: str) -> PlanillaEscaneada:
        if not motivo.strip():
            raise ValueError("Indicá por qué se descarta la planilla.")
        with self._candado:
            planilla = self._pendiente(planilla_id)
            descartada = replace(planilla, estado="DESCARTADA", revisada_por=actor,
                                 revisada_en=datetime.now(UTC), motivo_descarte=motivo.strip())
            self._planillas.guardar_planilla(descartada)
            return descartada

    def _pendiente(self, planilla_id: str) -> PlanillaEscaneada:
        planilla = self._planillas.obtener_planilla(planilla_id)
        if planilla is None:
            raise LookupError("No existe la planilla")
        if planilla.estado != "PENDIENTE":
            raise ValueError("La planilla ya fue revisada.")
        return planilla
