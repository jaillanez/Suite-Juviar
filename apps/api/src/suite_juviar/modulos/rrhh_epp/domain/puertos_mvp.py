"""Puertos: lo que el dominio necesita del mundo exterior.

Cada uno tiene hoy un adaptador de prueba (YAML / SQLite) y va a tener después
uno real (Vistas de Nexus / PostgreSQL / motor de firma de plataforma). El
dominio depende de estas interfaces, nunca de las implementaciones.
"""

from __future__ import annotations

from typing import Protocol

from .modelos_mvp import ElementoEPP, Entrega, Firma, Legajo, RequisitoEPP


class RepositorioLegajos(Protocol):
    """Lectura del maestro de personal. SIEMPRE de solo lectura.

    Implementaciones:
      - LegajosYAML          (prueba, hoy)
      - LegajosNexusSQLServer (real, cuando exista la VPN y la Vista)
    """

    @property
    def fuente(self) -> str:
        """'SIMULADA' o 'NEXUS'. Se muestra en pantalla y va en la bitácora."""
        ...

    def obtener(self, legajo: str) -> Legajo | None: ...

    def buscar(self, texto: str, limite: int = 20) -> list[Legajo]:
        """Busca por número de legajo, apellido o DNI. Sólo activos."""
        ...


class RepositorioCatalogo(Protocol):
    """Catálogo RD 068/11 y matriz Puesto vs. EPP."""

    def obtener_elemento(self, codigo: str) -> ElementoEPP | None: ...

    def listar_elementos(self) -> list[ElementoEPP]: ...

    def requisitos_de_puesto(self, puesto_codigo: str) -> list[RequisitoEPP]: ...


class RepositorioEntregas(Protocol):
    def guardar(self, entrega: Entrega) -> None: ...

    def obtener(self, id_entrega: str) -> Entrega | None: ...

    def listar_por_legajo(self, legajo: str) -> list[Entrega]: ...


class MotorFirma(Protocol):
    """Vive en plataforma/firma, no acá (§5.3 de la base común).

    El adaptador de prueba devuelve firmas con `simulada=True`. El motor real
    tiene que devolver `simulada=False` y agregar la firma digital de la
    empresa con sello de tiempo.
    """

    @property
    def metodos_habilitados(self) -> tuple[str, ...]: ...

    def firmar_trabajador(self, metodo: str, evidencia: str, documento: dict) -> Firma: ...


class Bitacora(Protocol):
    """Regla 5 de la base: quién hizo qué y cuándo."""

    def registrar(self, evento: str, usuario: str, detalle: dict) -> None: ...
