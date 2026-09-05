"""Motor de firma: servicio compartido, no función de un módulo.

Base Común §5.3: la constancia de EPP, la declaración jurada y cualquier
conformidad futura usan el mismo motor. Se programa una vez, acá, y todos los
módulos lo invocan. Si cada módulo implementa la suya, van a convivir tres
criterios de validez legal y ninguna auditoría va a ser defendible.

Marco: Ley 25.506 y Disposición SRT 3/2022 (reemplazo de la planilla de papel
de la Res. SRT 299/2011 por constancia digital).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class TipoFirma(StrEnum):
    DIGITAL = "DIGITAL"        # empresa: certificado de entidad licenciada
    ELECTRONICA = "ELECTRONICA"  # trabajador: trazo, PIN o biometría


class MetodoFirmaElectronica(StrEnum):
    # PENDIENTE §5.2: elegir uno o combinarlos, con el asesor legal.
    TRAZO_TABLET = "TRAZO_TABLET"
    PIN_PERSONAL = "PIN_PERSONAL"
    BIOMETRIA_FACIAL = "BIOMETRIA_FACIAL"


@dataclass(frozen=True, slots=True)
class SelloDeTiempo:
    """Regla obligatoria §5.4.2: certificación cronológica del momento exacto."""

    emitido_en: datetime
    autoridad: str
    token: bytes


@dataclass(frozen=True, slots=True)
class Firma:
    documento_id: UUID
    tipo: TipoFirma
    firmante: str                  # legajo de Nexus, o CUIT si es un tercero
    hash_documento: str            # SHA-256 del PDF original, byte a byte
    sello: SelloDeTiempo
    metodo: MetodoFirmaElectronica | None = None
    geolocalizacion: tuple[float, float] | None = None  # refuerzo, no MVP
    id: UUID = field(default_factory=uuid4)
    aplicada_en: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class DocumentoFirmado:
    """El PDF original con su integridad intacta.

    Regla obligatoria §5.4.1: una impresión, una captura de pantalla o un PDF
    re-guardado destruyen la firma. Por eso `contenido` es bytes inmutables y
    no hay ningún método que lo reemplace: la única operación posible es
    emitir un documento nuevo que anule al anterior.
    """

    id: UUID
    tipo_documento: str            # "constancia_epp", "ddjj", ...
    contenido: bytes
    hash_sha256: str
    firmas: tuple[Firma, ...]
    anula_a: UUID | None = None
