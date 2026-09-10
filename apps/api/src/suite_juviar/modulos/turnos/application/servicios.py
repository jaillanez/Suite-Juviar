from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time
from uuid import uuid4

from ..domain.entidades import (
    CambioCronograma,
    Cronograma,
    DiaConciliado,
    EstadoDia,
    EstadoImputacion,
    Imputacion,
    SalidaBandeja,
)
from ..domain.puertos import ExportadorNovedades, FuenteFichadas


class ConciliarTurnos:
    def __init__(self, fuente: FuenteFichadas, exportador: ExportadorNovedades,
                 hoy=lambda: datetime.now(UTC)):
        self.fuente = fuente
        self.exportador = exportador
        self._ahora = hoy
        self.cronogramas: list[Cronograma] = []
        self.cambios: list[CambioCronograma] = []
        self.imputaciones: dict[str, Imputacion] = {}
        self.bandeja: list[SalidaBandeja] = []

    @property
    def simulada(self) -> bool:
        return self.fuente.simulada or self.exportador.simulada

    def cargar_cronograma(self, legajo: str, sector: str, fecha: date,
                          desde: time, hasta: time, autor: str) -> Cronograma:
        if fecha < self._ahora().date():
            raise ValueError("El día está cerrado: sólo se admite registrar un cambio tardío.")
        if hasta <= desde:
            raise ValueError("El fin del turno debe ser posterior al inicio.")
        fila = Cronograma(uuid4(), legajo, sector, fecha, desde, hasta, autor, self._ahora())
        self.cronogramas.append(fila)
        return fila

    def cargar_semana(self, sector: str, asignaciones: list[dict], autor: str) -> list[Cronograma]:
        return [self.cargar_cronograma(
            str(fila["legajo"]), sector, fila["fecha"], fila["desde"], fila["hasta"], autor
        ) for fila in asignaciones]

    def registrar_cambio_tardio(self, cronograma_id: str, desde: time, hasta: time,
                                autor: str, conocido_en: datetime | None = None) -> Cronograma:
        anterior = self._obtener_cronograma(cronograma_id)
        conocimiento = conocido_en or self._ahora()
        if conocimiento.date() <= anterior.fecha:
            raise ValueError("Un cambio tardío debe conocerse después del día afectado.")
        if hasta <= desde:
            raise ValueError("El fin del turno debe ser posterior al inicio.")
        nueva = Cronograma(uuid4(), anterior.legajo, anterior.sector, anterior.fecha,
                           desde, hasta, autor, conocimiento, anterior.id, True)
        self.cronogramas.append(nueva)
        self.cambios.append(CambioCronograma(
            uuid4(), nueva.id, anterior.legajo, anterior.sector, anterior.fecha,
            anterior.desde, anterior.hasta, desde, hasta, autor, conocimiento, True,
        ))
        return nueva

    def listar_cronogramas(self, *, sector: str | None = None, desde: date | None = None,
                           hasta: date | None = None) -> list[Cronograma]:
        return [plan for plan in self._cronogramas_activos()
                if (not sector or plan.sector.casefold() == sector.casefold())
                and (not desde or plan.fecha >= desde) and (not hasta or plan.fecha <= hasta)]

    def historial(self, *, sector: str | None = None) -> list[CambioCronograma]:
        return [c for c in self.cambios if not sector or c.sector.casefold() == sector.casefold()]

    def conciliar(self, desde: date, hasta: date, *, sector: str | None = None,
                  legajo: str | None = None) -> list[DiaConciliado]:
        por_dia = defaultdict(list)
        for fichada in self.fuente.listar(desde, hasta):
            por_dia[(fichada.legajo, fichada.momento.date())].append(fichada)
        resultado = []
        for plan in self.listar_cronogramas(sector=sector, desde=desde, hasta=hasta):
            if legajo and plan.legajo != legajo:
                continue
            marcas = sorted(por_dia[(plan.legajo, plan.fecha)], key=lambda f: f.momento)
            minutos_plan = int((datetime.combine(plan.fecha, plan.hasta) - datetime.combine(
                plan.fecha, plan.desde)).total_seconds() / 60)
            minutos_marcados = int((marcas[-1].momento - marcas[0].momento).total_seconds() / 60) if len(marcas) >= 2 else 0
            desvio = minutos_marcados - minutos_plan
            tipo = None
            propuesta_id = None
            if desvio:
                tipo = "AUSENCIA" if not marcas else "JORNADA_DIFERENTE"
                propuesta_id = self._propuesta(plan, desvio, tipo).id
            estado = EstadoDia.REGULARIZADO_TARDE if plan.cambio_tardio else (
                EstadoDia.SIN_INFORMAR if desvio else EstadoDia.PLANIFICADO)
            resultado.append(DiaConciliado(
                plan.legajo, plan.sector, plan.fecha, plan.desde, plan.hasta,
                marcas[0].momento if marcas else None, marcas[-1].momento if marcas else None,
                minutos_plan, minutos_marcados, desvio, tipo, estado, propuesta_id,
            ))
        return resultado

    def listar_propuestas(self, *, estado: EstadoImputacion | None = None) -> list[Imputacion]:
        return [x for x in self.imputaciones.values() if estado is None or x.estado is estado]

    def resolver_lote(self, ids: list[str], accion: str, actor_rrhh: str,
                      motivo_cambio: str | None = None) -> SalidaBandeja | None:
        if not ids:
            raise ValueError("Debe seleccionar al menos una propuesta.")
        try:
            seleccion = [self.imputaciones[i] for i in ids]
        except KeyError as exc:
            raise LookupError("Propuesta inexistente.") from exc
        if any(x.estado is not EstadoImputacion.PROPUESTA for x in seleccion):
            raise ValueError("Sólo se pueden resolver propuestas pendientes.")
        accion = accion.upper()
        if accion not in {"APROBAR", "RECHAZAR", "CAMBIAR"}:
            raise ValueError("Acción de lote inválida.")
        if accion == "CAMBIAR" and not (motivo_cambio or "").strip():
            raise ValueError("Cambiar la imputación requiere indicar el motivo final.")
        ahora = self._ahora()
        for imputacion in seleccion:
            imputacion.estado = EstadoImputacion.RECHAZADA if accion == "RECHAZAR" else EstadoImputacion.APROBADA
            imputacion.aprobada_por = actor_rrhh
            imputacion.resuelta_en = ahora
            imputacion.motivo_final = motivo_cambio.strip() if accion == "CAMBIAR" and motivo_cambio else imputacion.motivo_propuesto
        if accion == "RECHAZAR":
            return None
        archivo = self.exportador.exportar(seleccion)
        salida = SalidaBandeja(uuid4(), ahora, "GENERADO",
                               "JSON de intercambio — contrato pendiente", archivo,
                               len(seleccion), tuple(sorted({x.legajo for x in seleccion})),
                               self.exportador.simulada)
        self.bandeja.append(salida)
        return salida

    def aprobar_lote(self, ids: list[str], actor_rrhh: str) -> str:
        salida = self.resolver_lote(ids, "APROBAR", actor_rrhh)
        return salida.archivo if salida else ""

    def reporte_tardias(self, desde: date, hasta: date) -> dict[str, object]:
        conteo = Counter(c.sector for c in self.cambios
                         if c.tardio and desde <= c.fecha_afectada <= hasta)
        return {"desde": desde, "hasta": hasta, "por_sector": [
            {"sector": sector, "dias_regularizados_tarde": cantidad}
            for sector, cantidad in sorted(conteo.items())]}

    def antiguedad_pendiente(self, imputacion: Imputacion) -> int:
        return max(0, (self._ahora().date() - imputacion.fecha).days)

    def _propuesta(self, plan: Cronograma, desvio: int, tipo: str) -> Imputacion:
        existente = next((x for x in self.imputaciones.values()
                          if x.legajo == plan.legajo and x.fecha == plan.fecha), None)
        if existente:
            return existente
        motivo = "Ausencia contra cronograma" if tipo == "AUSENCIA" else "Jornada distinta del plan"
        propuesta = Imputacion(uuid4(), plan.legajo, plan.fecha, motivo, desvio,
                               sector=plan.sector, creada_en=self._ahora())
        self.imputaciones[str(propuesta.id)] = propuesta
        return propuesta

    def _obtener_cronograma(self, identificador: str) -> Cronograma:
        plan = next((x for x in self.cronogramas if str(x.id) == identificador), None)
        if plan is None:
            raise LookupError("Cronograma inexistente.")
        return plan

    def _cronogramas_activos(self) -> list[Cronograma]:
        reemplazados = {x.reemplaza_id for x in self.cronogramas if x.reemplaza_id}
        return sorted([x for x in self.cronogramas if x.id not in reemplazados],
                      key=lambda x: (x.fecha, x.sector, x.legajo))
