from __future__ import annotations

from typing import Protocol
from uuid import UUID

from .entidades import DocumentoFirmado, Firma, MetodoFirmaElectronica, SelloDeTiempo


class ProveedorSelloDeTiempo(Protocol):
    async def sellar(self, hash_documento: str) -> SelloDeTiempo: ...


class MotorDeFirma(Protocol):
    async def firmar_como_empresa(
        self, documento_id: UUID, contenido: bytes, firmante: str
    ) -> Firma: ...

    async def firmar_como_trabajador(
        self,
        documento_id: UUID,
        contenido: bytes,
        legajo: str,
        metodo: MetodoFirmaElectronica,
        evidencia: bytes,
    ) -> Firma: ...


class RepositorioDocumentos(Protocol):
    """Almacén de documentos firmados. Sin `actualizar`: son inmutables."""

    async def guardar(self, documento: DocumentoFirmado) -> None: ...

    async def obtener(self, documento_id: UUID) -> DocumentoFirmado | None: ...
