from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime
from uuid import UUID, uuid5

from suite_juviar.plataforma.firma.domain.entidades import MetodoFirmaElectronica
from suite_juviar.plataforma.firma.domain.puertos import MotorDeFirma

from ..domain.modelos import AlertaSupervisor, AnulacionAsistencia, Asistencia, Participante
from ..domain.puertos import ConfiguracionAsistencia, RepositorioCapacitacion

ESPACIO_DOCUMENTOS = UUID("aa1d75e7-1789-4ff5-b7d6-e5c3e040c6ce")


class RegistrarAsistencia:
    def __init__(self, repositorio: RepositorioCapacitacion, firma: MotorDeFirma) -> None:
        self._repositorio = repositorio
        self._firma = firma

    async def ejecutar(
        self,
        dictado_id: str,
        participante: Participante,
        presente: bool,
        metodo: MetodoFirmaElectronica | None = None,
        evidencia: bytes | None = None,
    ) -> Asistencia:
        dictado = self._repositorio.obtener_dictado(dictado_id)
        if dictado is None:
            raise ValueError("No existe el dictado")
        firma_id = None
        estado = "AUSENTE"
        if presente and metodo is None:
            estado = "PENDIENTE_FIRMA_PAPEL"
        elif presente:
            if not evidencia:
                raise ValueError("La asistencia electrónica requiere evidencia")
            contenido = json.dumps(
                {
                    "dictado": dictado.id,
                    "tema": dictado.tema_id,
                    "fecha": dictado.fecha.isoformat(),
                    "legajo": participante.legajo,
                    "marca": "DOCUMENTO DE PRUEBA - SIN VALIDEZ LEGAL",
                },
                sort_keys=True,
            ).encode()
            firma = await self._firma.firmar_como_trabajador(
                uuid5(ESPACIO_DOCUMENTOS, f"{dictado.id}:{participante.legajo}"),
                contenido,
                participante.legajo,
                metodo,
                evidencia,
            )
            firma_id = firma.id
            estado = self._firma.estado
        asistencia = Asistencia(dictado_id, participante, presente, firma_id, estado)
        self._repositorio.guardar_asistencia(asistencia)
        return asistencia


class ReportesCapacitacion:
    def __init__(
        self,
        repositorio: RepositorioCapacitacion,
        configuracion: ConfiguracionAsistencia,
    ) -> None:
        self._repositorio = repositorio
        self._configuracion = configuracion

    def porcentaje_tema(self, tema_id: str) -> float:
        registros = [
            asistencia
            for dictado in self._repositorio.dictados_del_tema(tema_id)
            for asistencia in self._repositorio.asistencias_del_dictado(dictado.id)
        ]
        return self._porcentaje(registros)

    def porcentaje_persona(self, legajo: str) -> float:
        registros = [
            asistencia
            for asistencia in self._repositorio.todas_las_asistencias()
            if asistencia.participante.legajo == legajo
        ]
        return self._porcentaje(registros)

    def horas_por_persona(self, legajo: str, anio: int) -> float:
        total = 0.0
        for asistencia in self._repositorio.todas_las_asistencias():
            if asistencia.participante.legajo != legajo or not asistencia.presente:
                continue
            dictado = self._repositorio.obtener_dictado(asistencia.dictado_id)
            if dictado is None or dictado.fecha.year != anio:
                continue
            tema = self._repositorio.obtener_tema(dictado.tema_id)
            total += tema.horas if tema else 0
        return total

    def alertas_supervisores(self) -> list[AlertaSupervisor]:
        por_tema_y_legajo: dict[tuple[str, str], list[Asistencia]] = defaultdict(list)
        for asistencia in self._repositorio.todas_las_asistencias():
            if not asistencia.participante.supervisor:
                continue
            dictado = self._repositorio.obtener_dictado(asistencia.dictado_id)
            if dictado:
                por_tema_y_legajo[(dictado.tema_id, asistencia.participante.legajo)].append(
                    asistencia
                )
        return [
            AlertaSupervisor(tema, legajo, porcentaje, self._configuracion.umbral_supervisor)
            for (tema, legajo), registros in por_tema_y_legajo.items()
            if (porcentaje := self._porcentaje(registros)) < self._configuracion.umbral_supervisor
        ]

    @staticmethod
    def _porcentaje(registros: list[Asistencia]) -> float:
        if not registros:
            return 0.0
        return round(100 * sum(registro.presente for registro in registros) / len(registros), 2)


class AnularAsistencia:
    def __init__(self, repositorio: RepositorioCapacitacion) -> None:
        self._repositorio = repositorio

    def ejecutar(
        self,
        dictado_id: str,
        legajo: str,
        motivo: str,
        actor: str,
    ) -> AnulacionAsistencia:
        existente = next(
            (
                asistencia
                for asistencia in self._repositorio.asistencias_del_dictado(dictado_id)
                if asistencia.participante.legajo == legajo
            ),
            None,
        )
        if existente is None:
            raise ValueError("No existe la asistencia que se intenta anular")
        anulacion = AnulacionAsistencia(
            dictado_id=dictado_id,
            legajo=legajo,
            motivo=motivo,
            anulada_por=actor,
            anulada_en=datetime.now(UTC),
        )
        self._repositorio.anular_asistencia(anulacion)
        return anulacion


def planilla_imprimible(tema: str, fecha: date) -> str:
    return (
        "DOCUMENTO DE PRUEBA - SIN VALIDEZ LEGAL\n"
        f"Tema: {tema}\nFecha: {fecha.isoformat()}\n"
        "Legajo | Apellido y nombre | Presente | Firma\n"
    )
