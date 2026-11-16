"""Piezas puras de la oferta de uva y de "Mis turnos" por WhatsApp.

El productor ofrece los kilos de cada variedad para toda la temporada. El bot no
reserva días: la oferta queda pendiente y la bodega le asigna los días desde Gestión
(infra/038). Las reglas de verdad (rangos, certificado orgánico, permiso del teléfono)
viven en la base; acá sólo se arma la conversación.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import uuid4

SEDES: tuple[tuple[str, str], ...] = (
    ("chimbas", "Chimbas"),
    ("lavalle", "Lavalle"),
    ("media-agua", "Media Agua"),
)
NOMBRE_SEDE = dict(SEDES)

KG_MIN_OFERTA, KG_MAX_OFERTA = 1_000, 50_000_000
VARIEDADES_MOSTRADAS = 8

_DIAS_SEMANA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


@dataclass(frozen=True)
class Borrador:
    """Lo que el productor ya respondió en la oferta. Se guarda entre mensajes."""

    pedido: str = field(default_factory=lambda: str(uuid4()))
    sede: str | None = None
    lineas: tuple[tuple[str, int], ...] = ()   # (variedad, kilos) ya ofrecidas
    variedad: str | None = None                # la que se está cargando
    opciones: tuple[str, ...] = ()             # variedades mostradas, en orden
    organica: bool | None = None

    def a_dict(self) -> dict:
        return {
            "pedido": self.pedido,
            "sede": self.sede,
            "lineas": [list(linea) for linea in self.lineas],
            "variedad": self.variedad,
            "opciones": list(self.opciones),
            "organica": self.organica,
        }

    @classmethod
    def desde_dict(cls, datos: dict | None) -> Borrador | None:
        # Un borrador del pedido de turno anterior (por día) no tiene "pedido": se descarta.
        if not datos or "pedido" not in datos:
            return None
        return cls(
            pedido=datos["pedido"],
            sede=datos.get("sede"),
            lineas=tuple((str(v), int(kg)) for v, kg in datos.get("lineas") or ()),
            variedad=datos.get("variedad"),
            opciones=tuple(datos.get("opciones") or ()),
            organica=datos.get("organica"),
        )

    @property
    def total(self) -> int:
        return sum(kg for _, kg in self.lineas)


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


@dataclass(frozen=True)
class OfertaVigente:
    id: int
    sede: str
    clientecuit: str
    codigo: str | None
    variedad: str
    kg: int
    estado: str                    # pendiente | asignada | detenida | desestimada
    detenida_hasta: date | None = None


class OfertaRechazada(Exception):
    """La base no aceptó la oferta; el mensaje es el de la regla que no se cumplió."""


class Turnos(Protocol):
    def tiene_organico(self, clientecuit: str, fecha: date) -> bool: ...

    def variedades(self, clientecuit: str) -> list[str]:
        """Las que entregó en las últimas temporadas, la más entregada primero."""
        ...

    def ofrecer(
        self, pedido: str, clientecuit: str, codigo: str, sede: str, variedad: str, kg: int,
        organica: bool,
    ) -> OfertaVigente: ...

    def ofertas(self, clientecuits: list[str]) -> list[OfertaVigente]:
        """Las de la temporada que viene, que no estén desestimadas."""
        ...

    def proximos(self, clientecuits: list[str], desde: date) -> list[TurnoVigente]: ...


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


def kilos_escritos(texto: str | None) -> int | None:
    """Kilos: "80000", "80.000", "80 000 kg", "80 t", "12,5 toneladas"."""
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
    texto = re.sub(r"\d{4,}", lambda m: miles(int(m.group())), texto)
    texto = texto[0].upper() + texto[1:]
    return texto if texto.endswith(".") else texto + "."
