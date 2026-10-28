"""Reglas puras de conversación del bot de productores."""

from __future__ import annotations

import unicodedata
from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("America/Argentina/San_Juan")
MENU = (
    "Escribí el número de lo que querés consultar:\n"
    "1 — Descargas de hoy\n"
    "2 — Última descarga\n"
    "3 — Camiones en báscula"
)
NO_REGISTRADO = (
    "Este número no está registrado para consultar descargas. "
    "Comunicate con la bodega para darlo de alta."
)


class Consultas(Protocol):
    def ultima(self, clientecuit: str): ...
    def del_dia(self, clientecuit: str, dia: date) -> list: ...
    def en_descarga(self, clientecuit: str) -> list: ...
    def datos_al(self) -> dict[str, datetime]: ...


def _normalizar(texto: str | None) -> str:
    base = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    return "".join(caracter for caracter in base if not unicodedata.combining(caracter))


def intencion(texto: str | None) -> str:
    normalizado = _normalizar(texto)
    if normalizado in {"1", "hoy"} or "hoy" in normalizado:
        return "hoy"
    if normalizado in {"2", "ultima"} or "ultima" in normalizado:
        return "ultima"
    if normalizado == "3" or "camion" in normalizado or "bascula" in normalizado:
        return "en_curso"
    return "menu"


def _kg(valor: int | None) -> str:
    return f"{(valor or 0):,} kg".replace(",", ".")


def _hora(valor: datetime | None) -> str:
    return valor.strftime("%d/%m %H:%M") if valor else "sin fecha"


def _datos_al(consultas: Consultas) -> str:
    marcas = consultas.datos_al()
    if not marcas:
        return "\n\n(sin sincronización registrada)"
    mas_vieja = min(marcas.values()).astimezone(ZONA)
    return f"\n\nDatos actualizados al {mas_vieja:%d/%m %H:%M}."


def responder(
    texto: str | None, productores: list[str], consultas: Consultas, hoy: date
) -> str:
    if not productores:
        return NO_REGISTRADO
    que = intencion(texto)
    if que == "menu":
        return MENU + _datos_al(consultas)

    bloques: list[str] = []
    for indice, clientecuit in enumerate(productores, start=1):
        encabezado = f"Productor {indice}" if len(productores) > 1 else ""
        if que == "hoy":
            filas = consultas.del_dia(clientecuit, hoy)
            cuerpo = (
                f"Hoy: {len(filas)} descarga(s), "
                f"{_kg(sum(fila.neto or 0 for fila in filas))} netos."
                if filas
                else "Hoy no hay descargas terminadas."
            )
        elif que == "ultima":
            fila = consultas.ultima(clientecuit)
            cuerpo = (
                f"Última descarga: {_hora(fila.fecha)}, {_kg(fila.neto)}, "
                f"{fila.variedad or 's/variedad'}"
                + (f", azúcar {fila.azucar:g}" if fila.azucar is not None else "")
                + "."
                if fila
                else "No hay descargas registradas."
            )
        else:
            filas = consultas.en_descarga(clientecuit)
            cuerpo = (
                f"{len(filas)} camión(es) en báscula ahora."
                if filas
                else "No hay camiones tuyos en báscula ahora."
            )
        bloques.append(f"{encabezado}\n{cuerpo}".strip())
    return "\n\n".join(bloques) + _datos_al(consultas)
