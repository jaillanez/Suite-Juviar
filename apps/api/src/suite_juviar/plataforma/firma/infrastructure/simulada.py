"""Motor explícitamente simulado para pruebas; ninguna firma tiene validez legal."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from ..domain.entidades import Firma, MetodoFirmaElectronica, SelloDeTiempo, TipoFirma


class MotorFirmaSimulado:
    estado = "SIMULADO_SIN_VALIDEZ_LEGAL"

    @staticmethod
    def _firma(
        documento_id: UUID,
        contenido: bytes,
        firmante: str,
        tipo: TipoFirma,
        metodo: MetodoFirmaElectronica | None,
    ) -> Firma:
        digest = hashlib.sha256(contenido).hexdigest()
        ahora = datetime.now(UTC)
        return Firma(
            documento_id=documento_id,
            tipo=tipo,
            firmante=firmante,
            hash_documento=digest,
            sello=SelloDeTiempo(
                emitido_en=ahora,
                autoridad="SIMULADA",
                token=f"SIMULADO:{digest}".encode(),
            ),
            metodo=metodo,
            aplicada_en=ahora,
        )

    async def firmar_como_empresa(
        self,
        documento_id: UUID,
        contenido: bytes,
        firmante: str,
    ) -> Firma:
        return self._firma(documento_id, contenido, firmante, TipoFirma.DIGITAL, None)

    async def firmar_como_trabajador(
        self,
        documento_id: UUID,
        contenido: bytes,
        legajo: str,
        metodo: MetodoFirmaElectronica,
        evidencia: bytes,
    ) -> Firma:
        if not evidencia:
            raise ValueError("La evidencia de firma no puede estar vacía")
        return self._firma(
            documento_id,
            contenido + evidencia,
            legajo,
            TipoFirma.ELECTRONICA,
            metodo,
        )

