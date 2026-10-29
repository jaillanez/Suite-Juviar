"""Piezas puras del pedido de turnos por WhatsApp.

Las reglas de verdad (días, rangos, cupo del día, certificado orgánico) viven en la
base: ``fila.reservar_turno_whatsapp`` usa la misma función que Gestión. Acá sólo se
arma la conversación y se valida lo justo para no hacer preguntar de más.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

SEDES: tuple[tuple[str, str], ...] = (
    ("chimbas", "Chimbas"),
    ("lavalle", "Lavalle"),
    ("media-agua", "Media Agua"),
)
NOMBRE_SEDE = dict(SEDES)

DIAS_OFRECIDOS = 7        # cuántos días con lugar se muestran
DIAS_A_MIRAR = 14         # hasta dónde se buscan esos días
DIAS_MAXIMOS = 60         # misma anticipación que la base
CAMIONES_MAX = 50
KG_MIN_CAMION, KG_MAX_CAMION = 1_000, 40_000
KG_POR_DEFECTO = 11_000

_DIAS_SEMANA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


@dataclass(frozen=True)
class Borrador:
    """Lo que el productor ya respondió. Se guarda entre mensajes."""

    sede: str | None = None
    fecha: date | None = None
    camiones: int | None = None
    kg_por_camion: int | None = None
    kg_sugerido: int | None = None
    organica: bool | None = None
    dias: tuple[date, ...] = ()   # los días que se le ofrecieron, en el orden mostrado

    def a_dict(self) -> dict:
        return {
            "sede": self.sede,
            "fecha": self.fecha.isoformat() if self.fecha else None,
            "camiones": self.camiones,
            "kg_por_camion": self.kg_por_camion,
            "kg_sugerido": self.kg_sugerido,
            "organica": self.organica,
            "dias": [d.isoformat() for d in self.dias],
        }

    @classmethod
    def desde_dict(cls, datos: dict | None) -> Borrador | None:
        if not datos:
            return None
        return cls(
            sede=datos.get("sede"),
            fecha=date.fromisoformat(datos["fecha"]) if datos.get("fecha") else None,
            camiones=datos.get("camiones"),
            kg_por_camion=datos.get("kg_por_camion"),
            kg_sugerido=datos.get("kg_sugerido"),
            organica=datos.get("organica"),
            dias=tuple(date.fromisoformat(d) for d in datos.get("dias") or ()),
        )


@dataclass(frozen=True)
class TurnoVigente:
    id: int
    sede: str
    fecha: date
    clientecuit: str
    codigo: str | None
    camiones: int
    camiones_usados: int
    kg_por_camion: int
    organica: bool


class TurnoRechazado(Exception):
    """La base no aceptó el turno; el mensaje es el de la regla que no se cumplió."""


class Turnos(Protocol):
    def libres(self, sede: str, desde: date, hasta: date) -> dict[date, int]:
        """Kilos libres por día. Sólo trae los días con capacidad definida."""
        ...

    def tiene_organico(self, clientecuit: str, fecha: date) -> bool: ...

    def kg_estimado(self, clientecuit: str) -> int: ...

    def proximos(self, clientecuits: list[str], desde: date) -> list[TurnoVigente]: ...

    def reservar(
        self,
        clientecuit: str,
        codigo: str,
        sede: str,
        fecha: date,
        camiones: int,
        kg_por_camion: int,
        organica: bool,
    ) -> TurnoVigente: ...


def _normalizar(texto: str | None) -> str:
    limpio = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    return "".join(c for c in limpio if not unicodedata.combining(c))


def miles(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def toneladas(kg: int) -> str:
    if kg % 1000 == 0:
        return f"{kg // 1000} t"
    return f"{kg / 1000:.1f} t".replace(".", ",")


def dia_corto(dia: date, hoy: date) -> str:
    if dia == hoy:
        return f"Hoy {dia:%d/%m}"
    if dia == hoy + timedelta(days=1):
        return f"Mañana {dia:%d/%m}"
    return f"{_DIAS_SEMANA[dia.weekday()][:3].capitalize()} {dia:%d/%m}"


def dia_largo(dia: date) -> str:
    return f"{_DIAS_SEMANA[dia.weekday()]} {dia:%d/%m}"


def fecha_escrita(texto: str | None, hoy: date) -> date | None:
    """Entiende "hoy", "mañana", "pasado mañana", "30/10", "30-10" y "30/10/2026".

    Sin año, toma la próxima vez que cae ese día (un 02/01 escrito en diciembre es
    del año que viene).
    """
    t = _normalizar(texto)
    if t == "hoy":
        return hoy
    if t in {"manana", "mañana"}:
        return hoy + timedelta(days=1)
    if t == "pasado manana":
        return hoy + timedelta(days=2)
    m = re.fullmatch(r"(?:\w+\s+)?(\d{1,2})\s*[/.-]\s*(\d{1,2})(?:\s*[/.-]\s*(\d{2}|\d{4}))?", t)
    if not m:
        return None
    dia, mes = int(m.group(1)), int(m.group(2))
    try:
        if m.group(3):
            anio = int(m.group(3))
            return date(anio + 2000 if anio < 100 else anio, mes, dia)
        candidata = date(hoy.year, mes, dia)
        if candidata < hoy:
            candidata = date(hoy.year + 1, mes, dia)
        return candidata
    except ValueError:
        return None


def entero_escrito(texto: str | None) -> int | None:
    """Primer número del texto: "3", "3 camiones", "son 3"."""
    m = re.search(r"\d+", _normalizar(texto))
    return int(m.group()) if m else None


def kilos_escritos(texto: str | None) -> int | None:
    """Kilos por camión: "12000", "12.000", "12 000 kg", "12 t", "12,5 toneladas"."""
    t = _normalizar(texto)
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(t|tn|ton|tonelada|toneladas)", t)
    if m:
        return int(Decimal(m.group(1).replace(",", ".")) * 1000)
    m = re.fullmatch(r"(\d{1,3}(?:[.\s]\d{3})+|\d+)\s*(kg|kgs|kilo|kilos)?", t)
    if m:
        return int(re.sub(r"[.\s]", "", m.group(1)))
    return None


def motivo_en_palabras(motivo: str) -> str:
    """Pasa el mensaje de la regla de la base a algo que se lea bien en el chat."""
    texto = (motivo or "").strip() or "la bodega no aceptó el pedido"
    if texto.startswith("sin cupo:"):
        texto = "no alcanza el lugar de ese día:" + texto[len("sin cupo:"):]
    texto = re.sub(r"\d{4,}", lambda m: miles(int(m.group())), texto)
    texto = texto[0].upper() + texto[1:]
    return texto if texto.endswith(".") else texto + "."
