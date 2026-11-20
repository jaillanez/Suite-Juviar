from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from .modelos import Confirmacion, CVEntrante, MensajeEntrante, MensajeRRHH


class RepositorioBandeja(Protocol):
    def guardar(self, mensaje: MensajeRRHH) -> None: ...

    def obtener(self, mensaje_id: str) -> MensajeRRHH | None: ...

    def listar(self) -> list[MensajeRRHH]: ...


class PuertaDMZ(Protocol):
    """Lo que el bot deja en la base de la fila y lo que Gestión le devuelve (infra/042)."""

    def tomar_mensajes(self) -> list[MensajeEntrante]: ...

    def confirmar_mensajes(self, ids: list[str]) -> None: ...

    def avisar_lectura(self, mensaje_id: str, texto: str, pide_confirmacion: bool) -> None: ...

    def confirmaciones(self, ids: list[str]) -> dict[str, Confirmacion]: ...

    def tomar_cvs(self) -> list[CVEntrante]: ...

    def confirmar_cvs(self, ids: list[str]) -> None: ...

    def recorridos(self) -> list[dict[str, Any]]: ...

    def guardar_recorrido(self, recorrido_id: int | None, sede: str, nombre: str, activo: bool,
                          actor: str) -> dict[str, Any]: ...

    def personal(self) -> list[dict[str, Any]]:
        """Personal activo del bot con su recorrido (sólo lo necesario para asignarlo)."""
        ...

    def asignar_recorrido(self, telefono: str, recorrido_id: int | None, actor: str) -> dict[str, Any]: ...


class DestinoSalud(Protocol):
    """Salud laboral: donde termina el certificado, con el diagnóstico (secreto médico)."""

    def cargar(self, legajo: str, diagnostico_codigo: str, desde: date, hasta: date, dias: int,
               profesional: str, nombre_adjunto: str, contenido: bytes, resumen: str,
               tipo_accidente: str) -> str:
        """Devuelve el id del certificado en Salud; ValueError si Salud lo rechaza."""
        ...

    def auditar(self, actor: str, legajo: str | None, accion: str) -> None: ...
