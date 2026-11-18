from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .modelos import Activo, Movimiento, Reparacion, Sector, TipoActivo
from .remitos import MensajeWhatsapp, ParametrosRemitos, Remito


class RepositorioActivos(Protocol):
    tipos: MutableMapping[str, TipoActivo]
    sectores: MutableMapping[str, Sector]
    activos: MutableMapping[str, Activo]
    reparaciones: MutableMapping[str, Reparacion]

    def registrar_movimiento(self, movimiento: Movimiento) -> None: ...

    def movimientos(self) -> list[Movimiento]: ...


class Impresora(Protocol):
    def enviar(self, zpl: str) -> None: ...


class RepositorioRemitos(Protocol):
    remitos: MutableMapping[str, Remito]
    mensajes: MutableMapping[str, MensajeWhatsapp]
    parametros: MutableMapping[str, ParametrosRemitos]


@dataclass(frozen=True, slots=True)
class Salida:
    salio_en: datetime
    salio_por: str


@dataclass(frozen=True, slots=True)
class MensajeEntrante:
    id: str
    telefono: str
    nombre: str
    texto: str
    recibido_en: datetime
    foto: bytes | None = None
    foto_tipo: str = ""


class PuertaGuardia(Protocol):
    """Lo que la guardia de cada bodega ve y marca en su consola (base de la fila)."""

    def publicar(self, remito: Remito) -> None: ...

    def anular(self, remito_id: str, actor: str) -> None: ...

    def salidas(self, remito_ids: list[str]) -> dict[str, Salida]: ...

    def tomar_mensajes(self) -> list[MensajeEntrante]: ...

    def confirmar_mensajes(self, ids: list[str]) -> None: ...
