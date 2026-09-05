"""Lo que la recepción le cuenta al resto del sistema.

Nadie importa este módulo: estos eventos viajan por el outbox y los consume
quien quiera (el modelo de lectura del bot, cosecha, analítica).
"""

RECEPCION_ROMANEO_ABIERTO = "recepcion.romaneo.abierto"
RECEPCION_ROMANEO_CERRADO = "recepcion.romaneo.cerrado"
RECEPCION_ROMANEO_ANULADO = "recepcion.romaneo.anulado"
RECEPCION_PRODUCTOR_SIN_VERIFICACION = "recepcion.productor.sin_verificacion"
