from __future__ import annotations

from collections.abc import MutableMapping
from typing import Protocol

from .modelos import Aviso, Compra, Demora, Parametros, Viaje


class RepositorioMosto(Protocol):
    compras: MutableMapping[str, Compra]
    viajes: MutableMapping[str, Viaje]
    avisos: MutableMapping[str, Aviso]
    parametros: MutableMapping[str, Parametros]


class Notificador(Protocol):
    """Canal de aviso: devuelve el resultado (enviado, encolado, sin_configurar) o lanza error."""

    canal: str

    def enviar(self, destino: str, demora: Demora) -> str: ...
