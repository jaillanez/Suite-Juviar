"""Plantillas de WhatsApp para los mensajes que inicia la empresa.

Meta sólo entrega un mensaje que inicia la empresa fuera de la ventana de 24 h (desde el último
mensaje de la persona) si es una plantilla aprobada. Acá están todas: el worker las manda por
Meta con los parámetros que deja la base (infra/043) y ``registrar_plantillas`` las envía a
revisión. Si Meta todavía no aprobó una, el worker manda el texto de siempre.

Reglas de Meta que cumplen los textos: las variables son ``{{1}}``, ``{{2}}``… en orden, ninguna
al principio ni al final del cuerpo, y cada una con su ejemplo. Los parámetros no pueden tener
saltos de línea ni más de cuatro espacios seguidos (``parametros_limpios``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

IDIOMA = "es_AR"
CATEGORIA = "UTILITY"
MAXIMO_PARAMETRO = 200


@dataclass(frozen=True)
class Plantilla:
    nombre: str
    cuerpo: str
    ejemplos: tuple[str, ...]
    descripcion: str  # para quién y cuándo sale (sólo para nosotros; Meta no lo ve)
    categoria: str = CATEGORIA
    idioma: str = IDIOMA

    @property
    def variables(self) -> int:
        return len(set(re.findall(r"\{\{(\d+)\}\}", self.cuerpo)))

    def texto(self, parametros: list[str] | tuple[str, ...]) -> str:
        """El mensaje como lo ve la persona (para las pruebas y para revisar los textos)."""
        return re.sub(r"\{\{(\d+)\}\}", lambda m: parametros[int(m.group(1)) - 1], self.cuerpo)

    def para_registrar(self) -> dict:
        """Cuerpo de ``POST /{cuenta}/message_templates``."""
        return {
            "name": self.nombre,
            "language": self.idioma,
            "category": self.categoria,
            "components": [
                {"type": "BODY", "text": self.cuerpo, "example": {"body_text": [list(self.ejemplos)]}}
            ],
        }


TURNOS_ASIGNADOS = Plantilla(
    nombre="turnos_asignados",
    cuerpo=("Hola, {{1}}. La bodega {{2}} te asignó los días para tu {{3}}: del {{4}} al {{5}} "
            "(sin domingos), {{6}} en total. El detalle de cada día está en «Mis turnos» de este WhatsApp."),
    ejemplos=("Pérez Juan", "Chimbas", "Syrah", "lunes 02/03", "sábado 07/03", "12 camiones"),
    descripcion="Al productor, cuando la bodega le asigna los días de una oferta (infra/038).",
)

OFERTA_POSTERGADA = Plantilla(
    nombre="oferta_postergada",
    cuerpo=("Hola, {{1}}. La bodega {{2}} postergó tu {{3}} porque todavía le falta grado. "
            "Te vamos a asignar días nuevos a partir del {{4}}. Los vas a ver en «Mis turnos»."),
    ejemplos=("Pérez Juan", "Chimbas", "Syrah", "lunes 16/03"),
    descripcion="Al productor, cuando la bodega detiene una oferta por falta de grado (infra/038).",
)

MOSTO_VIRGEN_DEMORADO = Plantilla(
    nombre="mosto_virgen_demorado",
    cuerpo=("URGENTE mosto virgen: el camión {{1}} ({{2}}, compra N.º {{3}}) lleva {{4}} h en {{5}} "
            "sin descargarse. Hay que descargarlo o pasarlo al concentrador."),
    ejemplos=("AB123CD", "Viñedos del Sur", "4512", "6.5", "Chimbas"),
    descripcion="Al personal elegido en Parámetros de Mosto, cuando un camión pasa las horas límite (infra/040).",
)

LLEGADA_MICRO = Plantilla(
    nombre="llegada_micro",
    cuerpo="Llegó el micro de personal del recorrido «{{1}}».",
    ejemplos=("Rawson",),
    descripcion="Al personal del recorrido, cuando la guardia toca «Llegó el micro» (infra/042).",
)

CATALOGO: dict[str, Plantilla] = {
    p.nombre: p for p in (TURNOS_ASIGNADOS, OFERTA_POSTERGADA, MOSTO_VIRGEN_DEMORADO, LLEGADA_MICRO)
}


def parametros_limpios(parametros) -> list[str]:
    """Texto de cada parámetro como lo acepta Meta: sin saltos de línea ni espacios de más."""
    return [re.sub(r"\s+", " ", str(p)).strip()[:MAXIMO_PARAMETRO] for p in parametros]


def armar(nombre: str | None, parametros) -> tuple[Plantilla, list[str]] | None:
    """La plantilla y sus parámetros listos, o None si no hay plantilla o los datos no cierran
    (entonces el aviso sale como texto)."""
    plantilla = CATALOGO.get(nombre or "")
    if plantilla is None or not isinstance(parametros, list | tuple):
        return None
    limpios = parametros_limpios(parametros)
    if len(limpios) != plantilla.variables or not all(limpios):
        return None
    return plantilla, limpios
