from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

MARCA_SIMULADA = "DATOS SIMULADOS — SIN VALIDEZ"


@dataclass(frozen=True, slots=True)
class PersonaLegajo:
    legajo: str
    nombre_completo: str
    empresa: str
    sector: str
    puesto: str


@dataclass(frozen=True, slots=True)
class Adjunto:
    id: str
    legajo: str
    nombre: str
    contenido: bytes
    activo: bool = True
    dado_baja_por: str | None = None
    dado_baja_en: datetime | None = None
    motivo_baja: str | None = None

    def dar_baja(self, motivo: str, actor: str) -> Adjunto:
        if not motivo.strip():
            raise ValueError("La baja lógica requiere un motivo.")
        return Adjunto(
            self.id, self.legajo, self.nombre, self.contenido, False,
            actor, datetime.now(UTC), motivo.strip(),
        )


class FuenteSimuladaEnProduccion(Exception):
    pass
