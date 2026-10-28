"""Registra el webhook sólo después de validar el circuito completo."""

from __future__ import annotations

import sys

from . import transporte
from .chattigo import ClienteChattigo, ConfigChattigo
from .webhook import cargar_secreto


def main(argumentos: list[str]) -> int:
    if len(argumentos) != 2 or not argumentos[1].startswith("https://"):
        print("uso: python -m consulta_publica.bot.configurar_webhook https://DOMINIO/webhook/chattigo")
        return 2
    if transporte.modo() != "chattigo":
        print(
            "BOT_TRANSPORTE no es 'chattigo'. Cambiarlo y reiniciar el worker "
            "antes de registrar el webhook."
        )
        return 1
    url = f"{argumentos[1].rstrip('/')}/{cargar_secreto()}"
    respuesta = ClienteChattigo(ConfigChattigo.desde_entorno()).configurar_webhook(url)
    print("Webhook registrado para el canal", respuesta.get("waId"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
