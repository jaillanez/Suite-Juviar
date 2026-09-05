"""Modelos del dominio de RRHH / Higiene y Seguridad.

Sin dependencias de framework ni de base de datos a propósito: este paquete
no importa nada de `adaptadores` ni de `api`. Así el día que cambie la fuente
de legajos o el motor de base, esto no se toca.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

# --------------------------------------------------------------------------
# Personas: vienen de Nexus. El módulo las lee, nunca las crea ni las edita.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Legajo:
    legajo: str
    nombre: str
    apellido: str
    dni: str
    puesto_codigo: str
    puesto: str
    sector_codigo: str
    sector: str
    empresa: str
    tipo_vinculo: str
    activo: bool

    @property
    def nombre_completo(self) -> str:
        return f"{self.apellido}, {self.nombre}"


# --------------------------------------------------------------------------
# Catálogo RD 068/11 y matriz Puesto vs. EPP
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ElementoEPP:
    """Una fila del catálogo RD 068/11."""

    codigo: str
    producto: str
    tipo_modelo: str
    marca: str
    posee_certificacion: bool
    certificacion: str | None
    unidad: str
    vida_util_dias: int | None


@dataclass(frozen=True)
class RequisitoEPP:
    """Lo que le corresponde a un puesto según la matriz de Higiene y Seguridad."""

    codigo: str
    cantidad: int
    frecuencia: str          # SEMESTRAL | ANUAL | A_DEMANDA
    temporada: str           # VERANO | INVIERNO | TODO_EL_ANIO
    obligatorio: bool


# --------------------------------------------------------------------------
# Entrega
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class LineaEntrega:
    """Una fila de la grilla del RD 062/11.

    Los datos del producto se copian del catálogo al momento de la entrega, no
    se referencian. Si mañana cambia la marca del guante en el catálogo, la
    constancia vieja tiene que seguir diciendo qué se entregó ese día.
    """

    codigo: str
    producto: str
    tipo_modelo: str
    marca: str
    posee_certificacion: bool
    certificacion: str | None
    cantidad: int


@dataclass(frozen=True)
class Firma:
    """Conformidad del trabajador.

    `simulada` en True significa que la firma NO tiene validez legal: se
    capturó en el entorno de prueba, sin el motor de firma de la base
    (plataforma/firma) ni sello de tiempo de una autoridad.
    """

    metodo: str              # TRAZO_TABLET | PIN | BIOMETRIA
    evidencia: str           # trazo en base64, hash del PIN, id de la validación
    sello_tiempo: datetime
    simulada: bool


@dataclass(frozen=True)
class Entrega:
    id: str
    legajo: Legajo
    lineas: tuple[LineaEntrega, ...]
    fecha_entrega: date
    firma_trabajador: Firma
    usuario_deposito: str
    firma_empresa: str | None = None   # la firma digital del empleador la pone
                                       # el motor de la base, todavía no existe
    observaciones: str = ""

    @property
    def cantidad_items(self) -> int:
        return sum(l.cantidad for l in self.lineas)


# --------------------------------------------------------------------------
# Errores del dominio
# --------------------------------------------------------------------------

class ErrorDeEntrega(Exception):
    """Base de los rechazos de negocio. La API los traduce a HTTP 400/404."""


class LegajoInexistente(ErrorDeEntrega):
    pass


class LegajoInactivo(ErrorDeEntrega):
    pass


class EntregaSinLineas(ErrorDeEntrega):
    pass


class CodigoFueraDeCatalogo(ErrorDeEntrega):
    """Regla 3 de la base: no se acepta texto libre donde hay catálogo."""


class CantidadInvalida(ErrorDeEntrega):
    pass


class FirmaFaltante(ErrorDeEntrega):
    pass


class MetodoDeFirmaNoHabilitado(ErrorDeEntrega):
    pass
