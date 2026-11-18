"""Remito de salida de equipos y herramientas a talleres externos (reunión del 15-11, punto 5).

Reglas:
* Nada sale de la planta sin un remito autorizado por el Encargado de Mantenimiento.
  Firma en el celular (queda la imagen de la firma) o en papel (autoriza en Gestión y
  firma a mano el remito impreso).
* La guardia de la bodega ve los remitos autorizados y marca la salida en su consola.
* El remito lleva equipos con código y herramientas sin etiqueta descritas a mano;
  de todo se controla que vuelva.
* Lo que llega por WhatsApp (foto y texto) entra como borrador o directo para firmar,
  según Parámetros.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .modelos import BODEGAS

_TELEFONO = re.compile(r"^\d{8,20}$")
FIRMA_MAXIMA = 300_000  # bytes de la imagen PNG de la firma
FOTO_MAXIMA = 3_000_000


class EstadoRemito(StrEnum):
    BORRADOR = "BORRADOR"  # cargado, falta que lo autorice el Encargado
    AUTORIZADO = "AUTORIZADO"  # firmado: la guardia lo puede dejar salir
    AFUERA = "AFUERA"  # salió de la planta; quedan cosas por volver
    CERRADO = "CERRADO"  # volvió todo
    ANULADO = "ANULADO"


class ModoFirma(StrEnum):
    CELULAR = "celular"
    PAPEL = "papel"


class ModoWhatsapp(StrEnum):
    REVISION = "revision"  # entra como borrador y el Encargado lo completa
    DIRECTO = "directo"  # entra listo para firmar


@dataclass(frozen=True, slots=True)
class ItemRemito:
    descripcion: str
    codigo: str | None = None  # equipo etiquetado; None = herramienta cargada a mano
    cantidad: int = 1
    volvio_en: datetime | None = None
    volvio_por: str = ""

    def __post_init__(self) -> None:
        if not self.descripcion or not self.descripcion.strip():
            raise ValueError("Cada ítem del remito necesita una descripción.")
        if not 1 <= self.cantidad <= 999:
            raise ValueError("La cantidad de cada ítem tiene que estar entre 1 y 999.")

    @property
    def afuera(self) -> bool:
        return self.volvio_en is None


@dataclass(frozen=True, slots=True)
class Firma:
    modo: ModoFirma
    por: str
    en: datetime
    imagen: bytes | None = None  # PNG de la firma en el celular

    def __post_init__(self) -> None:
        if self.modo is ModoFirma.CELULAR:
            if not self.imagen or not self.imagen.startswith(b"\x89PNG") or len(self.imagen) > FIRMA_MAXIMA:
                raise ValueError("Falta la firma dibujada en la pantalla.")
        elif self.imagen is not None:
            raise ValueError("La firma en papel no lleva imagen.")


@dataclass(frozen=True, slots=True)
class Remito:
    id: str
    numero: int
    bodega: str
    destino: str  # taller o lugar externo
    motivo: str
    items: tuple[ItemRemito, ...]
    creado_por: str
    creado_en: datetime
    origen: str = "gestion"  # gestion | whatsapp
    foto: bytes | None = None
    foto_tipo: str = ""
    firma: Firma | None = None
    salio_en: datetime | None = None
    salio_por: str = ""
    anulado_en: datetime | None = None
    anulado_por: str = ""
    anulado_motivo: str = ""

    def __post_init__(self) -> None:
        # Un borrador que llegó por WhatsApp puede venir incompleto; para firmar tiene que estar todo.
        if self.bodega and self.bodega not in BODEGAS:
            raise ValueError("Elegí la bodega de la que sale: Chimbas, Media Agua o Lavalle.")
        if self.firma is not None:
            self.validar_completo()
        if not 1 <= len(self.items) <= 50:
            raise ValueError("El remito tiene que llevar entre 1 y 50 ítems.")
        codigos = [i.codigo for i in self.items if i.codigo]
        if len(codigos) != len(set(codigos)):
            raise ValueError("Un mismo equipo no puede ir dos veces en el remito.")
        if self.foto is not None and len(self.foto) > FOTO_MAXIMA:
            raise ValueError("La foto es demasiado grande.")

    def validar_completo(self) -> None:
        if not self.bodega:
            raise ValueError("Elegí la bodega de la que sale: Chimbas, Media Agua o Lavalle.")
        if not self.destino.strip():
            raise ValueError("Indicá a qué taller o lugar va.")
        if not self.motivo.strip():
            raise ValueError("Indicá el motivo de la salida.")

    @property
    def estado(self) -> EstadoRemito:
        if self.anulado_en is not None:
            return EstadoRemito.ANULADO
        if self.firma is None:
            return EstadoRemito.BORRADOR
        if self.salio_en is None:
            return EstadoRemito.AUTORIZADO
        if any(i.afuera for i in self.items):
            return EstadoRemito.AFUERA
        return EstadoRemito.CERRADO


@dataclass(frozen=True, slots=True)
class ParametrosRemitos:
    # Días que algo puede estar afuera antes de marcarlo demorado; sin cargar, no hay aviso.
    dias_maximos_fuera: int | None = None
    modo_whatsapp: ModoWhatsapp = ModoWhatsapp.REVISION
    actualizado_por: str = ""
    actualizado_en: datetime | None = None

    def __post_init__(self) -> None:
        if self.dias_maximos_fuera is not None and not 1 <= self.dias_maximos_fuera <= 365:
            raise ValueError("Los días máximos afuera tienen que estar entre 1 y 365.")


@dataclass(frozen=True, slots=True)
class MensajeWhatsapp:
    """Foto y texto que mandó alguien de mantenimiento por WhatsApp."""

    id: str
    telefono: str
    nombre: str
    texto: str
    recibido_en: datetime
    foto: bytes | None = None
    foto_tipo: str = ""
    remito_id: str | None = None
    descartado_por: str = ""

    def __post_init__(self) -> None:
        if not _TELEFONO.match(self.telefono):
            raise ValueError("Teléfono inválido.")
