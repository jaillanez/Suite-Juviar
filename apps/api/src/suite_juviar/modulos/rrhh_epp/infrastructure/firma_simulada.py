"""Motor de firma SIMULADO.

Guarda el trazo o el PIN y le pone la hora del servidor. Nada más.

Lo que NO hace, y por eso ninguna constancia generada acá tiene validez legal:

  - no aplica la firma digital del empleador con certificado de entidad
    certificante licenciada (Ley 25.506),
  - no usa sello de tiempo de una autoridad, sólo el reloj de la máquina,
  - no genera el PDF firmado ni conserva metadatos de firma (§5.4 de la base).

El motor real vive en plataforma/firma y lo comparten EPP, DDJJ y cualquier
otra conformidad. Cuando exista, se reemplaza esta clase y se pone
simulada=False. Hasta entonces, todas las constancias salen marcadas.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from ..domain.modelos_mvp import Firma


class FirmaSimulada:
    """Métodos habilitados según §5.2 de la base: falta elegir cuál queda."""

    def __init__(self, metodos: tuple[str, ...] = ("TRAZO_TABLET", "PIN")) -> None:
        self._metodos = metodos

    @property
    def metodos_habilitados(self) -> tuple[str, ...]:
        return self._metodos

    def firmar_trabajador(self, metodo: str, evidencia: str, documento: dict) -> Firma:
        if metodo == "PIN":
            # Nunca se guarda el PIN en claro, ni siquiera en la prueba.
            evidencia = "sha256:" + hashlib.sha256(evidencia.encode("utf-8")).hexdigest()
        return Firma(
            metodo=metodo,
            evidencia=evidencia,
            sello_tiempo=datetime.now(UTC),
            simulada=True,
        )
