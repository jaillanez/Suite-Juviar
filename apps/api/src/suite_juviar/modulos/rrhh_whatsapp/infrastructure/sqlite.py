"""Bandeja de RRHH cifrada: certificados médicos y pedidos del personal (datos sensibles).

Cada mensaje (con su archivo y lo que se leyó) se guarda cifrado con AES-GCM, como los adjuntos
del legajo y de Salud.
"""

from __future__ import annotations

import os
import pickle
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from suite_juviar.plataforma.persistencia.sqlite_colecciones import (
    BaseColeccionesSQLite,
    MapaSQLite,
)

from ..domain.modelos import MensajeRRHH

_DATO_ASOCIADO = b"rrhh-whatsapp"


class BandejaCifradaMemoria:
    def __init__(self, clave: bytes) -> None:
        if len(clave) not in {16, 24, 32}:
            raise ValueError("La clave AES debe tener 16, 24 o 32 bytes.")
        self._aes = AESGCM(clave)
        self._filas: dict[str, tuple[bytes, bytes]] = {}

    def guardar(self, mensaje: MensajeRRHH) -> None:
        nonce = os.urandom(12)
        self._filas[mensaje.id] = (nonce, self._aes.encrypt(nonce, pickle.dumps(mensaje), _DATO_ASOCIADO))

    def _leer(self, fila: tuple[bytes, bytes]) -> MensajeRRHH:
        # Sólo se deserializa lo que escribió este mismo servidor: AES-GCM rechaza cualquier
        # contenido alterado o cifrado con otra clave antes de llegar a pickle.
        return pickle.loads(self._aes.decrypt(fila[0], fila[1], _DATO_ASOCIADO))

    def obtener(self, mensaje_id: str) -> MensajeRRHH | None:
        fila = self._filas.get(mensaje_id)
        return self._leer(fila) if fila else None

    def listar(self) -> list[MensajeRRHH]:
        return [self._leer(fila) for fila in self._filas.values()]

    def bytes_persistidos(self, mensaje_id: str) -> bytes:
        return self._filas[mensaje_id][1]


class BandejaCifradaSQLite(BandejaCifradaMemoria):
    def __init__(self, clave: bytes, ruta: str | Path) -> None:
        super().__init__(clave)
        self._filas = MapaSQLite(BaseColeccionesSQLite(ruta), "rrhh_whatsapp.mensajes")
