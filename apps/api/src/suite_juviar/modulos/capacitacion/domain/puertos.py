from __future__ import annotations

from typing import Protocol

from .modelos import AnulacionAsistencia, Asistencia, Dictado, FilaPlanilla, PlanillaEscaneada, Tema


class RepositorioCapacitacion(Protocol):
    def guardar_tema(self, tema: Tema) -> None: ...

    def guardar_dictado(self, dictado: Dictado) -> None: ...

    def guardar_asistencia(self, asistencia: Asistencia) -> None: ...

    def anular_asistencia(self, anulacion: AnulacionAsistencia) -> None: ...

    def obtener_anulacion(
        self,
        dictado_id: str,
        legajo: str,
    ) -> AnulacionAsistencia | None: ...

    def obtener_tema(self, tema_id: str) -> Tema | None: ...

    def obtener_dictado(self, dictado_id: str) -> Dictado | None: ...

    def dictados_del_tema(self, tema_id: str) -> list[Dictado]: ...

    def asistencias_del_dictado(self, dictado_id: str) -> list[Asistencia]: ...

    def todas_las_asistencias(self) -> list[Asistencia]: ...


class PersonaDelPadron(Protocol):
    legajo: str
    nombre_completo: str
    empresa: str
    sector: str
    puesto: str


class PadronPersonal(Protocol):
    """Personal activo según la fuente maestra de legajos."""

    @property
    def simulada(self) -> bool: ...

    def buscar(self, *, sector: str | None = None, empresa: str | None = None) -> list[PersonaDelPadron]: ...


class ConfiguracionAsistencia(Protocol):
    @property
    def estado(self) -> str: ...

    @property
    def dueno_dato(self) -> str: ...

    @property
    def umbral_supervisor(self) -> float: ...


class RepositorioPlanillas(Protocol):
    def guardar_planilla(self, planilla: PlanillaEscaneada) -> None: ...

    def guardar_archivo_planilla(self, planilla_id: str, contenido: bytes) -> None: ...

    def archivo_planilla(self, planilla_id: str) -> bytes | None: ...

    def obtener_planilla(self, planilla_id: str) -> PlanillaEscaneada | None: ...

    def listar_planillas(self) -> list[PlanillaEscaneada]: ...

    def confirmar_firma_papel(self, dictado_id: str, legajo: str) -> None: ...


class LectorPlanillas(Protocol):
    def leer(self, nombre: str, contenido: bytes, esperados: list[FilaPlanilla]) -> tuple[list[FilaPlanilla], str, str]:
        """Devuelve (filas leídas, motor usado, mensaje para quien revisa)."""
        ...
