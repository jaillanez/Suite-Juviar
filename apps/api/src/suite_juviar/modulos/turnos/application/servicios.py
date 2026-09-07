from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from uuid import uuid4

from ..domain.entidades import Cronograma, EstadoImputacion, Imputacion
from ..domain.puertos import ExportadorNovedades, FuenteFichadas


class ConciliarTurnos:
    def __init__(self, fuente: FuenteFichadas, exportador: ExportadorNovedades):
        self.fuente = fuente
        self.exportador = exportador
        self.cronogramas: list[Cronograma] = []
        self.imputaciones: dict[str, Imputacion] = {}

    @property
    def simulada(self) -> bool:
        return self.fuente.simulada or self.exportador.simulada

    def cargar_cronograma(self, legajo: str, sector: str, fecha: date, desde, hasta, autor: str):
        fila = Cronograma(legajo, sector, fecha, desde, hasta, autor, datetime.now(UTC))
        self.cronogramas.append(fila)
        return fila

    def conciliar(self, desde: date, hasta: date) -> list[Imputacion]:
        por_dia = defaultdict(list)
        for fichada in self.fuente.listar(desde, hasta):
            por_dia[(fichada.legajo, fichada.momento.date())].append(fichada)
        nuevas = []
        for plan in self.cronogramas:
            if not desde <= plan.fecha <= hasta:
                continue
            marcas = sorted(por_dia[(plan.legajo, plan.fecha)], key=lambda f: f.momento)
            minutos_plan = int(
                (datetime.combine(plan.fecha, plan.hasta) - datetime.combine(plan.fecha, plan.desde)).total_seconds() / 60
            )
            minutos_marcados = 0
            if len(marcas) >= 2:
                minutos_marcados = int((marcas[-1].momento - marcas[0].momento).total_seconds() / 60)
            desvio = minutos_marcados - minutos_plan
            if desvio:
                motivo = (
                    "ENFERMEDAD"
                    if any(marca.tipo == "CERTIFICADO_MEDICO" for marca in marcas)
                    else "LICENCIA" if not marcas else "CAMBIO_TURNO"
                )
                propuesta = Imputacion(uuid4(), plan.legajo, plan.fecha, motivo, desvio)
                self.imputaciones[str(propuesta.id)] = propuesta
                nuevas.append(propuesta)
        return nuevas

    def aprobar_lote(self, ids: list[str], actor_rrhh: str) -> str:
        seleccion = [self.imputaciones[i] for i in ids]
        for imputacion in seleccion:
            imputacion.estado = EstadoImputacion.APROBADA
            imputacion.aprobada_por = actor_rrhh
        return self.exportador.exportar(seleccion)
