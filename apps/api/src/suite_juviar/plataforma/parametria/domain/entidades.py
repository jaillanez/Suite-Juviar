"""Parametría: todo lo que puede cambiar sin desarrollo vive acá.

Si un umbral, un plazo o una vigencia está escrito en el código, cada cambio de
criterio operativo se convierte en un deploy. Estos valores se editan desde el
panel, quedan versionados y cada cambio deja bitácora.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class TipoParametro(StrEnum):
    ENTERO = "ENTERO"
    DECIMAL = "DECIMAL"
    TEXTO = "TEXTO"
    BOOLEANO = "BOOLEANO"
    DURACION_DIAS = "DURACION_DIAS"


@dataclass(frozen=True, slots=True)
class Parametro:
    clave: str
    tipo: TipoParametro
    valor: Any
    modulo: str
    descripcion: str
    editable_en_panel: bool = True
    vigente_desde: datetime = field(default_factory=lambda: datetime.now(UTC))


# Catálogo inicial. La lista es el contrato: si un módulo necesita un valor
# configurable nuevo, se agrega acá, no como constante en su código.
CATALOGO_INICIAL: tuple[Parametro, ...] = (
    Parametro(
        clave="recepcion.tolerancia_peso_kg",
        tipo=TipoParametro.DECIMAL,
        valor=Decimal(20),
        modulo="recepcion",
        descripcion="Diferencia admitida entre peso declarado y pesado antes de alertar.",
    ),
    Parametro(
        clave="recepcion.origen_peso_manual_habilitado",
        tipo=TipoParametro.BOOLEANO,
        valor=True,
        modulo="recepcion",
        descripcion=(
            "Permite carga manual del peso mientras no se confirme si la báscula "
            "tiene salida digital (pendiente §4.4)."
        ),
    ),
    Parametro(
        clave="epp.dias_aviso_vencimiento_entrega",
        tipo=TipoParametro.DURACION_DIAS,
        valor=15,
        modulo="rrhh_epp",
        descripcion="Antelación con la que se avisa el recambio de un elemento.",
    ),
    Parametro(
        clave="turnos.tolerancia_desvio_minutos",
        tipo=TipoParametro.ENTERO,
        valor=15,
        modulo="turnos",
        descripcion="Desvío entre turno planificado y marcada que no genera novedad.",
    ),
    Parametro(
        clave="consulta.minutos_vigencia_codigo",
        tipo=TipoParametro.ENTERO,
        valor=30,
        modulo="consulta",
        descripcion="Vigencia del código de acceso del productor al bot.",
    ),
)
