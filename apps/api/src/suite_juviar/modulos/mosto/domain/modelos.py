"""Compra de mosto a terceros, viajes que entran a planta y su liquidación por azúcar.

Reglas (reunión del 15-11):
* El laboratorio analiza la muestra de la oferta. Si Calidad la rechaza, el Jefe de
  Producción puede aprobarla para mezcla; con escasez de mercado decide Comercial.
* Aprobada la oferta, se ratifica pileta por pileta con su volumen.
* El precio base es sobre una referencia de azúcar (220 g/L) y se ajusta en proporción
  al azúcar real, menos un margen de resguardo (1 g/L) salvo excepción comercial.
* Al cerrar el contrato se promedia el azúcar de todos los viajes y se sugiere el precio.
* El mosto virgen fermenta: si un camión pasa el tiempo límite sin descargarse se avisa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

TIPOS = {"sulfitado": "Mosto sulfitado", "virgen": "Mosto virgen"}
BODEGAS = {"chimbas": "Chimbas", "media-agua": "Media Agua", "lavalle": "Lavalle"}
_CUIT = re.compile(r"^\d{11}$")
_PATENTE = re.compile(r"^[A-Z0-9]{5,10}$")
_TELEFONO = re.compile(r"^\d{8,20}$")
_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _obligatorio(nombre: str, valor: str | None) -> None:
    if not valor or not valor.strip():
        raise ValueError(f"{nombre} no puede estar vacío.")


@dataclass(frozen=True, slots=True)
class Analisis:
    azucar_gl: float
    actor: str
    fecha: datetime
    absorbancia_520: float | None = None
    alcohol: float | None = None
    observaciones: str = ""

    def __post_init__(self) -> None:
        if not 0 < self.azucar_gl < 1000:
            raise ValueError("El azúcar tiene que estar entre 0 y 1000 g/L.")
        if self.absorbancia_520 is not None and not 0 <= self.absorbancia_520 < 100:
            raise ValueError("La absorbancia a 520 nm tiene que estar entre 0 y 100.")
        if self.alcohol is not None and not 0 <= self.alcohol < 100:
            raise ValueError("El alcohol tiene que estar entre 0 y 100 %.")


class Etapa(StrEnum):
    CALIDAD = "calidad"
    PRODUCCION = "produccion"
    COMERCIAL = "comercial"


@dataclass(frozen=True, slots=True)
class Decision:
    etapa: Etapa
    aprueba: bool
    motivo: str
    actor: str
    fecha: datetime


@dataclass(frozen=True, slots=True)
class MuestraPileta:
    id: str
    pileta: str
    litros: float
    analisis: Analisis

    def __post_init__(self) -> None:
        _obligatorio("La pileta", self.pileta)
        if self.litros <= 0:
            raise ValueError("Los litros de la pileta tienen que ser más de cero.")


class EstadoCompra(StrEnum):
    EN_ANALISIS = "EN_ANALISIS"
    RECHAZADA_CALIDAD = "RECHAZADA_CALIDAD"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"
    CERRADA = "CERRADA"


@dataclass(frozen=True, slots=True)
class Liquidacion:
    litros: float
    azucar_promedio: float
    margen_gl: float
    azucar_liquidada: float
    azucar_referencia: float
    precio_base: float
    precio_litro: float
    total: float


@dataclass(frozen=True, slots=True)
class Compra:
    """Oferta de un proveedor; aprobada, es el contrato contra el que entran los viajes."""

    id: str
    numero: int
    proveedor: str
    cuit: str
    tipo: str
    litros: float
    precio_base: float
    creada_por: str
    creada_en: datetime
    analisis: Analisis | None = None
    decisiones: tuple[Decision, ...] = ()
    piletas: tuple[MuestraPileta, ...] = ()
    sin_margen: bool = False
    sin_margen_motivo: str = ""
    cerrada_en: datetime | None = None
    cerrada_por: str = ""
    liquidacion: Liquidacion | None = None

    def __post_init__(self) -> None:
        _obligatorio("El proveedor", self.proveedor)
        if not _CUIT.match(self.cuit):
            raise ValueError("El CUIT tiene que tener 11 números, sin guiones.")
        if self.tipo not in TIPOS:
            raise ValueError("Elegí el tipo: sulfitado o virgen.")
        if self.litros <= 0:
            raise ValueError("Los litros tienen que ser más de cero.")
        if self.precio_base <= 0:
            raise ValueError("El precio base tiene que ser más de cero.")

    @property
    def estado(self) -> EstadoCompra:
        if self.cerrada_en is not None:
            return EstadoCompra.CERRADA
        if not self.decisiones:
            return EstadoCompra.EN_ANALISIS
        ultima = self.decisiones[-1]
        if ultima.aprueba:
            return EstadoCompra.APROBADA
        return EstadoCompra.RECHAZADA_CALIDAD if ultima.etapa is Etapa.CALIDAD else EstadoCompra.RECHAZADA


@dataclass(frozen=True, slots=True)
class Paso:
    """Lugar de la planta por el que pasa el mosto: pileta, tanque o concentrador."""

    lugar: str
    actor: str
    fecha: datetime
    nota: str = ""


@dataclass(frozen=True, slots=True)
class Viaje:
    id: str
    compra_id: str
    bodega: str
    patente: str
    litros: float
    ingreso_por: str
    ingreso_en: datetime
    analisis: Analisis | None = None
    descarga: Paso | None = None
    recorrido: tuple[Paso, ...] = ()
    avisado_en: datetime | None = None

    def __post_init__(self) -> None:
        if self.bodega not in BODEGAS:
            raise ValueError("Elegí la bodega: Chimbas, Media Agua o Lavalle.")
        if not _PATENTE.match(self.patente):
            raise ValueError("La patente tiene que tener de 5 a 10 letras o números, sin espacios.")
        if self.litros <= 0:
            raise ValueError("Los litros del viaje tienen que ser más de cero.")


@dataclass(frozen=True, slots=True)
class Destinatario:
    nombre: str
    correo: str = ""
    telefono: str = ""

    def __post_init__(self) -> None:
        _obligatorio("El nombre de quien recibe el aviso", self.nombre)
        if not self.correo and not self.telefono:
            raise ValueError(f"Cargá el mail o el celular de {self.nombre}.")
        if self.correo and not _CORREO.match(self.correo):
            raise ValueError(f"El mail de {self.nombre} no es válido.")
        if self.telefono and not _TELEFONO.match(self.telefono):
            raise ValueError(f"El celular de {self.nombre} tiene que tener sólo números, con característica.")


@dataclass(frozen=True, slots=True)
class Parametros:
    azucar_referencia: float = 220
    margen_gl: float = 1
    # Sin horas cargadas no hay alarma: la bodega tiene que fijarlas.
    horas_virgen: float | None = None
    destinatarios: tuple[Destinatario, ...] = ()
    actualizado_por: str = ""
    actualizado_en: datetime | None = None

    def __post_init__(self) -> None:
        if not 0 < self.azucar_referencia < 1000:
            raise ValueError("El azúcar de referencia tiene que estar entre 0 y 1000 g/L.")
        if not 0 <= self.margen_gl < 50:
            raise ValueError("El margen tiene que estar entre 0 y 50 g/L.")
        if self.horas_virgen is not None and not 0 < self.horas_virgen <= 240:
            raise ValueError("Las horas límite del mosto virgen tienen que estar entre 0 y 240.")


@dataclass(frozen=True, slots=True)
class Envio:
    canal: str  # correo | whatsapp
    destino: str
    nombre: str
    resultado: str  # enviado | encolado | sin_configurar | error
    detalle: str = ""


@dataclass(frozen=True, slots=True)
class Aviso:
    id: str
    viaje_id: str
    texto: str
    creado_en: datetime
    envios: tuple[Envio, ...] = field(default=())


def azucar_liquidada(azucar: float, margen: float, sin_margen: bool) -> float:
    return azucar if sin_margen else max(azucar - margen, 0.0)


def precio_ajustado(precio_base: float, azucar: float, referencia: float) -> float:
    """Precio Base × (g/L de azúcar / referencia)."""
    return precio_base * azucar / referencia


def promedio_ponderado(pares: list[tuple[float, float]]) -> float:
    """Promedio de azúcar ponderado por litros: (litros, g/L)."""
    litros = sum(l for l, _ in pares)
    if litros <= 0:
        raise ValueError("No hay litros para promediar.")
    return sum(l * a for l, a in pares) / litros


def liquidar(compra: Compra, viajes: list[Viaje], parametros: Parametros) -> Liquidacion:
    analizados = [(v.litros, v.analisis.azucar_gl) for v in viajes if v.analisis is not None]
    if not analizados:
        raise ValueError("Ningún viaje tiene análisis de azúcar todavía.")
    promedio = promedio_ponderado(analizados)
    liquidada = azucar_liquidada(promedio, parametros.margen_gl, compra.sin_margen)
    precio = precio_ajustado(compra.precio_base, liquidada, parametros.azucar_referencia)
    litros = sum(v.litros for v in viajes)
    return Liquidacion(
        litros=litros, azucar_promedio=round(promedio, 2),
        margen_gl=0.0 if compra.sin_margen else parametros.margen_gl,
        azucar_liquidada=round(liquidada, 2), azucar_referencia=parametros.azucar_referencia,
        precio_base=compra.precio_base, precio_litro=round(precio, 4), total=round(precio * litros, 2),
    )
