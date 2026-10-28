from __future__ import annotations

from datetime import date

from ..domain.modelos_mvp import CircuitoEntregaInvalido, EntregaProgramada
from ..domain.puertos_mvp import RepositorioCatalogo, RepositorioLegajos


class PlanificarEntregasProgramadas:
    def __init__(self, legajos: RepositorioLegajos, catalogo: RepositorioCatalogo) -> None:
        self._legajos = legajos
        self._catalogo = catalogo

    def ejecutar(
        self,
        temporada: str,
        fecha: date,
        sector: str | None = None,
    ) -> list[EntregaProgramada]:
        if temporada not in {"VERANO", "INVIERNO"}:
            raise CircuitoEntregaInvalido("La temporada debe ser VERANO o INVIERNO.")
        salida: list[EntregaProgramada] = []
        for persona in self._legajos.listar_activos():
            if sector and persona.sector_codigo != sector:
                continue
            requisitos = tuple(
                requisito
                for requisito in self._catalogo.requisitos_de(
                    persona.sector_codigo,
                    persona.puesto_codigo,
                )
                if requisito.frecuencia == "SEMESTRAL"
                and requisito.temporada in {temporada, "TODO_EL_ANIO"}
            )
            if requisitos:
                salida.append(
                    EntregaProgramada(
                        fecha=fecha,
                        temporada=temporada,
                        trabajador=persona,
                        requisitos=requisitos,
                    )
                )
        return salida
