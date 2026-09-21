"""Planificación pura de altas, cambios, reapariciones y ausencias de Oracle."""

from __future__ import annotations

from dataclasses import dataclass, field

from .modelo import AUSENTE, FilaOrigen


class ClaveDuplicada(RuntimeError):
    pass


@dataclass(frozen=True)
class EstadoLocal:
    ciu: str
    huella: str
    estado: str


@dataclass
class Plan:
    nuevos: list[FilaOrigen] = field(default_factory=list)
    modificados: list[FilaOrigen] = field(default_factory=list)
    sin_cambio: list[str] = field(default_factory=list)
    ausentes: list[str] = field(default_factory=list)
    ausencias_suspendidas: str | None = None


def planificar(
    filas: list[FilaOrigen],
    locales: dict[str, EstadoLocal],
    *,
    minimo_filas: int,
    tope_ausencias: float,
) -> Plan:
    plan = Plan()
    vistos: set[str] = set()
    for fila in filas:
        if fila.ciu in vistos:
            raise ClaveDuplicada(f"CIU {fila.ciu} repetido en la sede {fila.sede}")
        vistos.add(fila.ciu)
        local = locales.get(fila.ciu)
        if local is None:
            plan.nuevos.append(fila)
        elif local.huella != fila.huella or local.estado == AUSENTE:
            plan.modificados.append(fila)
        else:
            plan.sin_cambio.append(fila.ciu)

    candidatos = [
        ciu for ciu, local in locales.items() if ciu not in vistos and local.estado != AUSENTE
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
