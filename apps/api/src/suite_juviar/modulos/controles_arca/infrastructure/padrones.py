"""Listados completos que publica ARCA: facturas apócrifas y agentes de retención (RG 18).

* Apócrifas: ``DownloadFile.aspx`` devuelve un ZIP con ``FacturasApocrifas.txt``
  (latin-1, separado por comas): ``CUIT, Fecha Condicion Apocrifo, Fecha Publicacion, Descripcion``.
* RG 18: ``Archivos/RG18.csv`` (latin-1, separado por punto y coma):
  ``CUIT;RAZON SOCIAL;FECHA_DESDE;FECHA_HASTA;INCISO_RG``.
"""

from __future__ import annotations

import io
import logging
import re
import threading
import zipfile

import httpx

from ..application.servicios import GestionarControles
from .arca import cliente_http

_registro = logging.getLogger(__name__)
MAXIMO_DESCARGA = 60 * 1024 * 1024
MAXIMO_DESCOMPRIMIDO = 200 * 1024 * 1024
_CUIT = re.compile(r"^\d{11}$")
_FECHA = re.compile(r"\d{2}/\d{2}/\d{4}(?: \d{2}:\d{2})?")

Registros = dict[str, tuple[tuple[str, ...], ...]]


def _agregar(registros: dict[str, list[tuple[str, ...]]], cuit: str, fila: tuple[str, ...]) -> None:
    registros.setdefault(cuit, []).append(fila)


def leer_apocrifas(contenido: bytes) -> tuple[str, Registros]:
    if contenido[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(contenido)) as archivo:
            textos = [i for i in archivo.infolist() if i.filename.lower().endswith(".txt")]
            if not textos:
                raise ValueError("El ZIP de apócrifas no trae el listado.")
            if textos[0].file_size > MAXIMO_DESCOMPRIMIDO:
                raise ValueError("El listado de apócrifas es demasiado grande.")
            contenido = archivo.read(textos[0])
    generado, registros = "", {}
    for linea in contenido.decode("latin-1").splitlines():
        linea = linea.strip()
        if linea.startswith("#"):
            if "Generado" in linea and (fecha := _FECHA.search(linea)):
                generado = fecha.group(0)
            continue
        partes = [p.strip() for p in linea.split(",")]
        if len(partes) >= 3 and _CUIT.match(partes[0]):
            _agregar(registros, partes[0], (partes[1], partes[2], partes[3] if len(partes) > 3 else ""))
    return generado, {c: tuple(f) for c, f in registros.items()}


def leer_rg18(contenido: bytes) -> tuple[str, Registros]:
    generado, registros = "", {}
    for numero, linea in enumerate(contenido.decode("latin-1").splitlines()):
        linea = linea.strip()
        if numero == 0 and (fecha := _FECHA.search(linea)):
            generado = fecha.group(0)
        partes = [p.strip() for p in linea.split(";")]
        if len(partes) >= 4 and _CUIT.match(partes[0]):
            _agregar(registros, partes[0], (partes[1], partes[2], partes[3], partes[4] if len(partes) > 4 else ""))
    return generado, {c: tuple(f) for c, f in registros.items()}


class DescargaHTTP:
    """Implementa ``DescargaPadrones``: baja con tope de tamaño y lee según el listado."""

    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http

    def descargar(self, nombre: str, url: str) -> tuple[str, Registros]:
        http = self._http or cliente_http()
        partes = []
        try:
            with http.stream("GET", url, timeout=httpx.Timeout(120.0, connect=15.0)) as respuesta:
                respuesta.raise_for_status()
                total = 0
                for parte in respuesta.iter_bytes():
                    total += len(parte)
                    if total > MAXIMO_DESCARGA:
                        raise ValueError("El listado de ARCA es demasiado grande.")
                    partes.append(parte)
        finally:
            if self._http is None:
                http.close()
        contenido = b"".join(partes)
        return leer_apocrifas(contenido) if nombre == "apocrifas" else leer_rg18(contenido)


def iniciar(servicio: GestionarControles, cada_segundos: int = 3600, horas: float = 24) -> threading.Thread:
    """Una vez por día baja los listados (revisa cada hora si ya pasaron 24 h)."""

    def ciclo() -> None:
        espera = 120  # deja arrancar la API antes de la primera descarga
        while True:
            threading.Event().wait(espera)
            espera = cada_segundos
            try:
                for nombre in servicio.actualizar_vencidos(horas):
                    _registro.info("Listado de ARCA actualizado: %s", nombre)
            except Exception:  # noqa: BLE001 - el ciclo no se corta por un error puntual
                _registro.exception("No se pudieron actualizar los listados de ARCA.")

    hilo = threading.Thread(target=ciclo, name="padrones-arca", daemon=True)
    hilo.start()
    return hilo
