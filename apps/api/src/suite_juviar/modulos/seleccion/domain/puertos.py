from __future__ import annotations

from typing import Protocol

from .modelos import (
    AvisoCoincidencia,
    CampoExtraido,
    CVOriginal,
    DocumentoEntrante,
    ExtraccionCV,
    PerfilBusqueda,
)


class FuenteCV(Protocol):
    @property
    def estado(self) -> str: ...

    def listar_nuevos(self) -> list[DocumentoEntrante]: ...


class RepositorioCVOriginales(Protocol):
    def guardar_original(self, original: CVOriginal) -> bool: ...

    def obtener_original(self, id_original: str) -> CVOriginal | None: ...

    def existe_referencia(self, referencia_fuente: str) -> bool: ...


class ExtractorTexto(Protocol):
    def extraer_texto(self, contenido: bytes) -> str: ...


class ExtractorCampos(Protocol):
    @property
    def estado(self) -> str: ...

    def extraer_campos(self, texto: str) -> list[CampoExtraido]: ...


class RepositorioExtracciones(Protocol):
    def guardar_extraccion(self, extraccion: ExtraccionCV) -> None: ...

    def obtener_extraccion(self, id_original: str) -> ExtraccionCV | None: ...


class CriteriosPerfil(Protocol):
    @property
    def estado(self) -> str: ...

    @property
    def dueno_dato(self) -> str: ...

    def palabras_clave(self, perfil: PerfilBusqueda) -> tuple[str, ...]: ...


class NotificadorCoincidencias(Protocol):
    def avisar(self, aviso: AvisoCoincidencia) -> None: ...
