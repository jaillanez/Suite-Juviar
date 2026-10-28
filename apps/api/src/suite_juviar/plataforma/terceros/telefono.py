"""Normalización de celulares argentinos al identificador usado por WhatsApp."""
from __future__ import annotations

import re

PREFIJO = "549"
LARGO_NACIONAL = 10


class TelefonoInvalido(ValueError):
    pass


def normalizar(texto: str | None) -> str:
    digitos = re.sub(r"\D", "", texto or "")
    if not digitos:
        raise TelefonoInvalido("falta el teléfono")
    digitos = digitos.removeprefix("00")
    if digitos.startswith("54"):
        digitos = digitos[2:]
        digitos = digitos.removeprefix("9")
    digitos = digitos.removeprefix("0")
    for largo_area in (2, 3, 4):
        if (
            len(digitos) > LARGO_NACIONAL
            and digitos[largo_area : largo_area + 2] == "15"
            and len(digitos) - 2 == LARGO_NACIONAL
        ):
            digitos = digitos[:largo_area] + digitos[largo_area + 2 :]
            break
    if len(digitos) != LARGO_NACIONAL:
        raise TelefonoInvalido(
            "el celular tiene que ser área + número, 10 dígitos en total "
            "(por ejemplo 2644567890)"
        )
    return PREFIJO + digitos


def para_mostrar(telefono: str) -> str:
    nacional = telefono.removeprefix(PREFIJO)
    return f"+54 9 {nacional[:3]} {nacional[3:]}"
