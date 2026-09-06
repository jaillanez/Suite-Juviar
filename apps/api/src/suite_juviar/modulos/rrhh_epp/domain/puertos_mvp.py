"""Puertos: lo que el dominio necesita del mundo exterior.

Cada uno tiene hoy un adaptador de prueba (YAML / SQLite) y va a tener después
uno real (Vistas de Nexus / PostgreSQL / motor de firma de plataforma). El
dominio depende de estas interfaces, nunca de las implementaciones.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .modelos_mvp import (
    DocumentoConstancia,
    ElementoEPP,
    Entrega,
    Firma,
    ItemCatalogo,
    Legajo,
    RequisitoEPP,
    SolicitudConstancia,
    StockItem,
)


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

    def listar_activos(self) -> list[Legajo]: ...


class RepositorioCatalogo(Protocol):
    """Catálogo RD 068/11 y matriz Puesto vs. EPP."""

    def obtener_elemento(self, codigo: str) -> ElementoEPP | None: ...

    def listar_elementos(self) -> list[ElementoEPP]: ...

    def obtener_item(self, codigo_interno: str) -> ItemCatalogo | None: ...

    def items_de(self, elemento_codigo: str) -> list[ItemCatalogo]: ...

    def requisitos_de(
        self,
        sector_codigo: str,
        puesto_codigo: str,
    ) -> list[RequisitoEPP]: ...

    def sector_definido(self, sector_codigo: str) -> bool: ...

    def nombre_sector(self, sector_codigo: str) -> str: ...

    def aplica_base(self, sector_codigo: str) -> bool: ...


class RepositorioEntregas(Protocol):
    def guardar(self, entrega: Entrega) -> bool:
        """Devuelve False si el identificador ya estaba persistido."""
        ...

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

    def firmar_trabajador(
        self,
        metodo: str,
        evidencia: str,
        documento: dict,
        sello_tiempo: datetime | None = None,
    ) -> Firma: ...


class GeneradorConstancia(Protocol):
    def generar(self, solicitud: SolicitudConstancia) -> DocumentoConstancia: ...


class RepositorioConstancias(Protocol):
    def obtener(self, id_entrega: str) -> DocumentoConstancia | None: ...

    def guardar_original(self, documento: DocumentoConstancia) -> None: ...


class RepositorioStock(Protocol):
    @property
    def estado(self) -> str: ...

    @property
    def dueno_dato(self) -> str: ...

    def listar(self) -> list[StockItem]: ...

    def obtener(self, item_codigo: str) -> StockItem | None: ...

    def verificar(self, lineas: list[tuple[str, int]]) -> None: ...

    def descontar(self, lineas: list[tuple[str, int]]) -> None: ...

    def configurar(self, item_codigo: str, disponible: int, minimo: int) -> StockItem: ...

    def alertas_pendientes(self) -> list[dict[str, object]]: ...


class ConfirmadorEntrega(Protocol):
    """Confirma entrega, stock y bitácora dentro de una única transacción."""

    def confirmar(
        self,
        entrega: Entrega,
        movimientos_stock: list[tuple[str, int]],
        evento: str,
        usuario: str,
        detalle: dict,
    ) -> bool:
        """Devuelve False si el identificador de entrega ya existía."""
        ...


class Bitacora(Protocol):
    """Regla 5 de la base: quién hizo qué y cuándo."""

    def registrar(self, evento: str, usuario: str, detalle: dict) -> None: ...
