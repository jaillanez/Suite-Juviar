"""Recuperar la contraseña de Gestión con un enlace que llega por correo.

El enlace lleva un código al azar de 256 bits que sirve una sola vez y vence a los 30
minutos; pedir otro anula los anteriores. Del código sólo se guarda el SHA-256.
"""

from __future__ import annotations

from datetime import timedelta

VIGENCIA_ENLACE = timedelta(minutes=30)
VENTANA_PEDIDOS = timedelta(hours=1)
PEDIDOS_POR_CORREO = 3  # por hora
PEDIDOS_POR_ORIGEN = 10  # por hora, sumando todos los correos pedidos desde el mismo equipo

RESPUESTA_PEDIDO = (
    "Si el correo está registrado, te mandamos un enlace para elegir una contraseña nueva. "
    "Revisá tu bandeja de entrada (y la de correo no deseado). El enlace vence en 30 minutos."
)
ASUNTO_CORREO = "Suite Juviar: elegí una contraseña nueva"


def cuerpo_correo(enlace: str) -> str:
    return (
        "Hola:\n\n"
        "Pediste elegir una contraseña nueva para entrar a Gestión de Suite Juviar. "
        "Abrí este enlace:\n\n"
        f"{enlace}\n\n"
        "El enlace vence en 30 minutos y sirve una sola vez.\n"
        "Si no lo pediste, ignorá este correo: tu contraseña no cambia.\n"
    )


class EnlaceDeRecuperacionInvalido(Exception):
    """El enlace no existe, ya se usó, venció o la cuenta está inactiva."""
