from __future__ import annotations

from collections.abc import MutableMapping
from typing import Protocol

from .modelos import (
    AccesoARCA,
    Constancia,
    Constatacion,
    Credencial,
    DatosCertificado,
    Factura,
    Padron,
    Parametros,
)


class RepositorioControles(Protocol):
    facturas: MutableMapping[str, Factura]
    parametros: MutableMapping[str, Parametros]
    archivos: MutableMapping[str, bytes]  # "<factura>:<control>" -> PDF
    padrones: MutableMapping[str, Padron]
    credenciales: MutableMapping[str, Credencial]  # "pendiente" | "activa"


class Cifrador(Protocol):
    def cifrar(self, valor: str) -> bytes: ...

    def descifrar(self, cifrado: bytes) -> str: ...


class Certificados(Protocol):
    def generar_pedido(self, cuit: str, alias: str, organizacion: str) -> tuple[str, str]:
        """Devuelve (clave privada PEM, pedido CSR PEM)."""
        ...

    def leer_certificado(self, certificado_pem: str, clave_pem: str) -> DatosCertificado:
        """Valida que el certificado sea de esa clave; lanza ValueError si no."""
        ...


class ConectorARCA(Protocol):
    def constancia(self, acceso: AccesoARCA, cuit_representada: str, cuit: str) -> Constancia: ...

    def constatar(self, acceso: AccesoARCA, cuit_representada: str, factura: Factura,
                  cuit_receptor: str) -> Constatacion: ...


class DescargaPadrones(Protocol):
    def descargar(self, nombre: str, url: str) -> tuple[str, dict[str, tuple[tuple[str, ...], ...]]]:
        """Baja y lee el listado: (fecha que trae el archivo, registros por CUIT)."""
        ...


class GeneradorPDF(Protocol):
    def constancia(self, titulo: str, filas: list[tuple[str, str]], alerta: bool) -> bytes: ...
