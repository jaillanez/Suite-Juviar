"""Cifrado AES-GCM de la clave privada del certificado de ARCA y de los permisos de WSAA.

Mismo esquema que la contraseña de Gmail de RRHH (``seleccion``), pero con clave derivada
y contexto propios: una filtración de un módulo no abre los secretos del otro.
"""

from __future__ import annotations

import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_CONTEXTO = b"controles-arca-certificado"
_SALT = b"suite-juviar-controles-arca"


class CifradorARCA:
    def __init__(self, clave: bytes) -> None:
        if len(clave) != 32:
            raise ValueError("La clave AES debe tener 32 bytes.")
        self._aes = AESGCM(clave)

    @classmethod
    def desde_secreto(cls, secreto: str) -> CifradorARCA:
        if not secreto:
            raise ValueError("Falta el secreto del servidor.")
        return cls(hashlib.scrypt(secreto.encode(), salt=_SALT, n=2**14, r=8, p=1, dklen=32))

    def cifrar(self, valor: str) -> bytes:
        nonce = os.urandom(12)
        return nonce + self._aes.encrypt(nonce, valor.encode(), _CONTEXTO)

    def descifrar(self, cifrado: bytes) -> str:
        return self._aes.decrypt(cifrado[:12], cifrado[12:], _CONTEXTO).decode()
