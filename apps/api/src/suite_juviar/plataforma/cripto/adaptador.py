"""Implementación de la protección de datos personales."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from suite_juviar.config import settings


class ProtectorAESGCM:
    """HMAC determinístico para índice + AES-256-GCM para el valor."""

    def __init__(self, clave_hmac: bytes, clave_cifrado: bytes) -> None:
        self._hmac = clave_hmac
        self._aead = AESGCM(clave_cifrado)

    def indice(self, valor: str) -> str:
        digest = hmac.new(self._hmac, valor.strip().encode(), hashlib.sha256).digest()
        return base64.b16encode(digest).decode()

    def cifrar(self, valor: str) -> bytes:
        nonce = os.urandom(12)
        return nonce + self._aead.encrypt(nonce, valor.encode(), None)

    def descifrar(self, cifrado: bytes) -> str:
        return self._aead.decrypt(cifrado[:12], cifrado[12:], None).decode()


def construir_protector() -> ProtectorAESGCM:
    return ProtectorAESGCM(
        clave_hmac=settings.hmac_datos_personales.encode(),
        clave_cifrado=hashlib.sha256(
            settings.clave_cifrado_datos_personales.encode()
        ).digest(),
    )
