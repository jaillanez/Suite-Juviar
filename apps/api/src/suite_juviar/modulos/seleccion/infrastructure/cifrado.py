"""Cifrado AES-GCM de parámetros secretos, como la contraseña de aplicación de Gmail."""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_CONTEXTO = b"seleccion-correo-rrhh"


class CifradorAESGCM:
    def __init__(self, clave: bytes) -> None:
        if len(clave) not in {16, 24, 32}:
            raise ValueError("La clave AES debe tener 16, 24 o 32 bytes.")
        self._aes = AESGCM(clave)

    def cifrar(self, valor: str) -> bytes:
        nonce = os.urandom(12)
        return nonce + self._aes.encrypt(nonce, valor.encode(), _CONTEXTO)

    def descifrar(self, cifrado: bytes) -> str:
        return self._aes.decrypt(cifrado[:12], cifrado[12:], _CONTEXTO).decode()
