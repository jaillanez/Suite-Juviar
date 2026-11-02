"""Etiquetas para impresoras Zebra: código de barras Code 128 en lenguaje ZPL.

Se usa código de barras y no QR porque en planta la suciedad tapa los QR.
La impresora recibe el ZPL por la red en el puerto 9100, que es el estándar de Zebra.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass

PUERTO_ZEBRA = 9100


class ErrorImpresora(RuntimeError):
    """Falla al hablar con la impresora, con un mensaje entendible en planta."""


@dataclass(frozen=True, slots=True)
class ConfiguracionEtiqueta:
    direccion: str
    puerto: int = PUERTO_ZEBRA
    dpi: int = 203
    ancho_mm: float = 100
    alto_mm: float = 50

    def __post_init__(self) -> None:
        try:
            ip = ipaddress.ip_address(self.direccion.strip())
        except ValueError:
            raise ValueError("La dirección de la impresora debe ser una IP, por ejemplo 192.168.1.50.") from None
        # Sólo impresoras de la red interna: el servidor no abre conexiones hacia afuera.
        if not ip.is_private or ip.is_loopback:
            raise ValueError("La impresora tiene que estar en la red interna de la planta.")
        if not 1 <= self.puerto <= 65535:
            raise ValueError("El puerto de la impresora no es válido.")
        if self.dpi not in {203, 300, 600}:
            raise ValueError("La resolución debe ser 203, 300 o 600 puntos por pulgada.")
        if not (20 <= self.ancho_mm <= 220 and 10 <= self.alto_mm <= 300):
            raise ValueError("El tamaño de la etiqueta no es válido.")


def _texto(valor: str, largo: int) -> str:
    # ^ y ~ son comandos en ZPL: no pueden aparecer dentro de un texto.
    limpio = " ".join(valor.replace("^", " ").replace("~", " ").split())
    return limpio if len(limpio) <= largo else limpio[: largo - 1] + "…"


def etiqueta_zpl(codigo: str, titulo: str, subtitulo: str, config: ConfiguracionEtiqueta, copias: int = 1) -> str:
    punto = config.dpi / 25.4
    ancho, alto = round(config.ancho_mm * punto), round(config.alto_mm * punto)
    margen = round(3 * punto)
    letra = max(20, round(alto * 0.12))
    chica = max(16, round(alto * 0.09))
    barras = max(40, alto - 2 * margen - letra - chica - round(alto * 0.22))
    # Ancho de cada barra: el más grueso que entra, así se lee aunque la etiqueta se ensucie.
    modulo = max(1, min(4, (ancho - 2 * margen) // (11 * (len(codigo) + 3) + 35)))
    caracteres = max(8, (ancho - 2 * margen) // max(1, round(letra * 0.55)))
    return "\n".join([
        "^XA",
        "^CI28",
        f"^PW{ancho}",
        f"^LL{alto}",
        f"^FO{margen},{margen}^A0N,{letra},{letra}^FD{_texto(titulo, caracteres)}^FS",
        f"^FO{margen},{margen + letra + 4}^A0N,{chica},{chica}^FD{_texto(subtitulo, caracteres + 8)}^FS",
        f"^FO{margen},{margen + letra + chica + 16}^BY{modulo}^BCN,{barras},Y,N,N^FD{_texto(codigo, 40)}^FS",
        f"^PQ{max(1, min(copias, 50))}",
        "^XZ",
    ])


class ImpresoraZebraRed:
    def __init__(self, direccion: str, puerto: int = PUERTO_ZEBRA, espera: float = 10) -> None:
        self._destino = (direccion, puerto)
        self._espera = espera

    def enviar(self, zpl: str) -> None:
        try:
            with socket.create_connection(self._destino, timeout=self._espera) as conexion:
                conexion.sendall(zpl.encode("utf-8"))
        except OSError as exc:
            raise ErrorImpresora(
                f"No se pudo conectar con la impresora en {self._destino[0]}. "
                "Revisá que esté encendida, con papel y en la red."
            ) from exc
