"""Máquina de estados de un viaje."""
from __future__ import annotations

TRANSICIONES: dict[str, set[str]] = {
    "pendiente": {"en_espera", "cancelado"},
    "en_espera": {"llamado", "cancelado"},
    "llamado": {"en_bascula", "en_espera", "cancelado"},
    "en_bascula": {"descargado", "cancelado"},
    "descargado": set(),
    "cancelado": set(),
}
ACTIVOS = {"pendiente", "en_espera", "llamado", "en_bascula"}
MINUTOS_VENCE_PENDIENTE = 30


class TransicionInvalida(ValueError):
    pass


def validar(desde: str, hacia: str) -> None:
    if hacia not in TRANSICIONES.get(desde, set()):
        raise TransicionInvalida(f"{desde} → {hacia} no está permitido")
