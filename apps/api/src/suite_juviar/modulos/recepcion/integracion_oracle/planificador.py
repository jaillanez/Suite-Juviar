"""Planificación pura de altas, cambios, reapariciones y ausencias de Oracle."""

from __future__ import annotations

from dataclasses import dataclass, field

from .modelo import AUSENTE, INCOMPLETO, ClaveDescarga, FilaOrigen


class ClaveDuplicada(RuntimeError):
    pass


@dataclass(frozen=True)
class EstadoLocal:
    ciu: str
    id_origen: str
    huella: str
    estado: str

    @property
    def clave(self) -> ClaveDescarga:
        return ClaveDescarga(self.ciu, self.id_origen)


@dataclass
class Plan:
    nuevos: list[FilaOrigen] = field(default_factory=list)
    modificados: list[FilaOrigen] = field(default_factory=list)
    sin_cambio: list[ClaveDescarga] = field(default_factory=list)
    ausentes: list[ClaveDescarga] = field(default_factory=list)
    ausencias_suspendidas: str | None = None


def planificar(
    filas: list[FilaOrigen],
    locales: dict[ClaveDescarga, EstadoLocal],
    *,
    minimo_filas: int,
    tope_ausencias: float,
) -> Plan:
    plan = Plan()
    vistos: set[ClaveDescarga] = set()
    for fila in filas:
        if fila.clave in vistos:
            raise ClaveDuplicada(
                f"clave (CIU={fila.ciu}, ID={fila.clave.id_origen}) repetida en {fila.sede}"
            )
        vistos.add(fila.clave)
        local = locales.get(fila.clave)
        if local and local.estado == INCOMPLETO and fila.valores["fecha"] is None:
            fila = fila.como_incompleta()
        if local is None:
            plan.nuevos.append(fila)
        elif local.huella != fila.huella or local.estado == AUSENTE:
            plan.modificados.append(fila)
        else:
            plan.sin_cambio.append(fila.clave)

    candidatos = [
        clave for clave, local in locales.items() if clave not in vistos and local.estado != AUSENTE
    ]
    if len(filas) < minimo_filas:
        plan.ausencias_suspendidas = f"lectura con {len(filas)} filas, mínimo {minimo_filas}"
    elif locales and len(candidatos) / len(locales) > tope_ausencias:
        plan.ausencias_suspendidas = (
            f"{len(candidatos)} de {len(locales)} filas ausentes supera el tope de "
            f"{tope_ausencias:.0%}; se requiere revisión manual"
        )
    else:
        plan.ausentes = candidatos
    return plan
