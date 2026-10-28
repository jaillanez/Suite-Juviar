from __future__ import annotations

import json
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

    def resumen_tema(self, tema_id: str, corte: date | None = None) -> dict[str, object]:
        dictados = self._repositorio.dictados_del_tema(tema_id)
        convocados = {legajo for d in dictados for legajo in d.convocados}
        asistentes = {
            a.participante.legajo
            for d in dictados
            for a in self._repositorio.asistencias_del_dictado(d.id)
            if a.presente
        }
        tiene_convocatoria = any(d.convocatoria_tipo for d in dictados)
        porcentaje = (
            round(100 * len(asistentes & convocados) / len(convocados), 2)
            if tiene_convocatoria and convocados
            else None
        )
        return {
            "tema_id": tema_id,
            "asistentes": len(asistentes),
            "convocados": len(convocados) if tiene_convocatoria else None,
            "porcentaje": porcentaje,
            "convocatoria": [
                {
                    "dictado_id": d.id,
                    "tipo": d.convocatoria_tipo,
                    "detalle": d.convocatoria_detalle,
                    "cantidad": len(d.convocados),
                }
                for d in dictados
                if d.convocatoria_tipo
            ],
            "fecha_corte": (corte or datetime.now(UTC).date()).isoformat(),
        }

    def porcentaje_tema(self, tema_id: str) -> float | None:
        return self.resumen_tema(tema_id)["porcentaje"]  # type: ignore[return-value]

    def porcentaje_persona(self, legajo: str) -> float | None:
        temas_convocados = {
            d.tema_id
            for tema in self._temas()
            for d in self._repositorio.dictados_del_tema(tema.id)
            if legajo in d.convocados
        }
        if not temas_convocados:
            return None
        temas_asistidos = {
            d.tema_id
            for a in self._repositorio.todas_las_asistencias()
            if a.participante.legajo == legajo
            and a.presente
            and (d := self._repositorio.obtener_dictado(a.dictado_id)) is not None
        }
        return round(100 * len(temas_asistidos & temas_convocados) / len(temas_convocados), 2)

    def horas_por_persona(self, legajo: str, anio: int) -> float:
        temas_contados: set[str] = set()
        for asistencia in self._repositorio.todas_las_asistencias():
            if asistencia.participante.legajo != legajo or not asistencia.presente:
                continue
            dictado = self._repositorio.obtener_dictado(asistencia.dictado_id)
            if dictado is None or dictado.fecha.year != anio:
                continue
            tema = self._repositorio.obtener_tema(dictado.tema_id)
            if tema:
                temas_contados.add(tema.id)
        return sum(
            self._repositorio.obtener_tema(t).horas
            for t in temas_contados
            if self._repositorio.obtener_tema(t)
        )

    def alertas_supervisores(self) -> list[AlertaSupervisor]:
        por_tema_y_legajo: dict[tuple[str, str], Participante] = {}
        for asistencia in self._repositorio.todas_las_asistencias():
            if not asistencia.participante.supervisor:
                continue
            dictado = self._repositorio.obtener_dictado(asistencia.dictado_id)
            if dictado:
                por_tema_y_legajo[(dictado.tema_id, asistencia.participante.legajo)] = (
                    asistencia.participante
                )
        return [
            AlertaSupervisor(tema, legajo, porcentaje, self._configuracion.umbral_supervisor)
            for (tema, legajo), _ in por_tema_y_legajo.items()
            if (porcentaje := self.porcentaje_persona_tema(legajo, tema)) is not None
            and porcentaje < self._configuracion.umbral_supervisor
        ]

    def recapacitaciones(self, corte: date | None = None) -> list[dict[str, object]]:
        fecha_corte = corte or datetime.now(UTC).date()
        ultimas: dict[tuple[str, str], tuple[date, str]] = {}
        for asistencia in self._repositorio.todas_las_asistencias():
            if not asistencia.presente:
                continue
            dictado = self._repositorio.obtener_dictado(asistencia.dictado_id)
            tema = self._repositorio.obtener_tema(dictado.tema_id) if dictado else None
            if not dictado or not tema or tema.periodicidad_meses is None:
                continue
            clave = (tema.id, asistencia.participante.legajo)
            if clave not in ultimas or dictado.fecha > ultimas[clave][0]:
                ultimas[clave] = (dictado.fecha, asistencia.participante.nombre_completo)
        avisos = []
        for (tema_id, legajo), (ultima, nombre) in ultimas.items():
            tema = self._repositorio.obtener_tema(tema_id)
            if tema is None or tema.periodicidad_meses is None:
                continue
            indice = ultima.year * 12 + ultima.month - 1 + tema.periodicidad_meses
            vencimiento = date(indice // 12, indice % 12 + 1, min(ultima.day, 28))
            if vencimiento <= fecha_corte:
                avisos.append({"tema_id": tema_id, "tema": tema.nombre, "legajo": legajo,
                               "nombre": nombre, "ultima_asistencia": ultima.isoformat(),
                               "recapacitar_desde": vencimiento.isoformat(), "dueno_periodicidad": "Higiene y Seguridad"})
        return avisos

    def porcentaje_persona_tema(self, legajo: str, tema_id: str) -> float | None:
        dictados = self._repositorio.dictados_del_tema(tema_id)
        if not any(legajo in d.convocados for d in dictados):
            return None
        asistio = any(
            a.participante.legajo == legajo and a.presente
            for d in dictados
            for a in self._repositorio.asistencias_del_dictado(d.id)
        )
        return 100.0 if asistio else 0.0

    def _temas(self):
        temas = getattr(self._repositorio, "temas", None)
        return list(temas.values()) if temas is not None else []

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
