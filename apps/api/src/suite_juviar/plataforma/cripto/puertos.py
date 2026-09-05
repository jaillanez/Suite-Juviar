"""Protección de datos personales: dos columnas por dato.

DNI, CUIT y cualquier identificador de persona se guardan como:

  * `<campo>_hmac`  — HMAC-SHA256 con clave secreta, determinístico. Es lo que
                      se indexa y por lo que se busca.
  * `<campo>_cif`   — el valor cifrado (AES-256-GCM), que solo se descifra
                      cuando hay que mostrarlo o imprimirlo.

La clave del HMAC vive fuera de la base (variable de entorno inyectada por el
orquestador, o KMS). Un dump de la base no alcanza para reconstruir los DNI.
"""

from __future__ import annotations

from typing import Protocol


class ProtectorDatosPersonales(Protocol):
    def indice(self, valor: str) -> str:
        """HMAC determinístico, apto para búsqueda e índice único."""
        ...

    def cifrar(self, valor: str) -> bytes: ...

    def descifrar(self, cifrado: bytes) -> str: ...
