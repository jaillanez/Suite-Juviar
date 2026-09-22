"""Claves y sesiones individuales de los guardias."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

ITERACIONES = 600_000
LARGO_SAL = 16
HORAS_SESION = 12
MAX_FALLOS = 10
LARGO_MINIMO_CLAVE = 6


class ClaveInvalida(ValueError):
    pass


def hashear(clave: str, sal: bytes | None = None) -> str:
    if len(clave) < LARGO_MINIMO_CLAVE:
        raise ClaveInvalida(f"la clave necesita al menos {LARGO_MINIMO_CLAVE} caracteres")
    sal = sal or secrets.token_bytes(LARGO_SAL)
    derivada = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal, ITERACIONES)
    return f"pbkdf2_sha256${ITERACIONES}${sal.hex()}${derivada.hex()}"


def verificar(clave: str, guardado: str) -> bool:
    if not clave or not guardado:
        return False
    try:
        algoritmo, iteraciones, sal, esperado = guardado.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        derivada = hashlib.pbkdf2_hmac(
            "sha256", clave.encode(), bytes.fromhex(sal), int(iteraciones)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derivada.hex(), esperado)


def nuevo_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def vencimiento(desde: datetime) -> datetime:
    return desde + timedelta(hours=HORAS_SESION)


@dataclass(frozen=True)
class Sesion:
    usuario: str
    sede: str
    vence: datetime

    @property
    def actor(self) -> str:
        return f"guardia:{self.usuario}"

    def vigente(self, ahora: datetime) -> bool:
        return ahora < self.vence

    def puede_operar(self, sede: str) -> bool:
        return self.sede == "*" or self.sede == sede
