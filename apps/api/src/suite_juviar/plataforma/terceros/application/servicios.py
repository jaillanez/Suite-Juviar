"""Puerto de aplicación para calificar compradores provenientes del sitio público."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from suite_juviar.plataforma.terceros.domain.entidades import TipoTercero


class ServicioTerceros(Protocol):
    def obtener_o_crear(
        self,
        *,
        tipo: TipoTercero,
        razon_social: str,
        pais: str,
        email: str,
        identificacion_fiscal: str | None,
    ) -> UUID: ...
