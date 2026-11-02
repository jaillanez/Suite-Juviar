"""Casilla de correo de RRHH por empresa: parámetros, prueba y lectura de CV.

La contraseña de aplicación se guarda cifrada y nunca vuelve a salir por la API.
"""

from __future__ import annotations

import re
from collections.abc import Callable, MutableMapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from ..domain.puertos import FuenteCV
from .extraccion import ExtraerDatosCV
from .ingesta import IngestarCVs

EMPRESAS = ("ENAV", "JUBIAR")
_CASILLA = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Cifrador(Protocol):
    def cifrar(self, valor: str) -> bytes: ...

    def descifrar(self, cifrado: bytes) -> str: ...


class BandejaConPrueba(FuenteCV, Protocol):
    def probar(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ResultadoLectura:
    empresa: str
    leida_en: datetime
    adjuntos: int
    incorporados: int
    repetidos: int
    error: str | None = None
    incompleta: bool = False  # quedaron correos para la próxima lectura


class CorreoRRHH:
    def __init__(
        self,
        parametros: MutableMapping[str, dict[str, Any]],
        cifrador: Cifrador,
        crear_bandeja: Callable[[str, str, datetime | None], BandejaConPrueba],
        ingestar: IngestarCVs,
        extraer: ExtraerDatosCV,
    ) -> None:
        self._parametros = parametros
        self._cifrador = cifrador
        self._crear_bandeja = crear_bandeja
        self._ingestar = ingestar
        self._extraer = extraer

    @staticmethod
    def _empresa(empresa: str) -> str:
        empresa = empresa.strip().upper()
        if empresa not in EMPRESAS:
            raise ValueError("Empresa desconocida.")
        return empresa

    def ver(self, empresa: str) -> dict[str, Any]:
        empresa = self._empresa(empresa)
        datos = self._parametros.get(empresa) or {}
        return {
            "empresa": empresa,
            "casilla": datos.get("casilla", ""),
            "clave_cargada": bool(datos.get("clave")),
            "actualizado_por": datos.get("actualizado_por"),
            "actualizado_en": datos.get("actualizado_en"),
            "ultima_lectura": datos.get("ultima_lectura"),
            "ultimo_resultado": datos.get("ultimo_resultado"),
        }

    def listar(self) -> list[dict[str, Any]]:
        return [self.ver(empresa) for empresa in EMPRESAS]

    def guardar(self, empresa: str, casilla: str, clave_aplicacion: str | None, actor: str) -> dict[str, Any]:
        empresa = self._empresa(empresa)
        casilla = casilla.strip().lower()
        if not _CASILLA.match(casilla):
            raise ValueError("La casilla de correo no es válida.")
        actual = dict(self._parametros.get(empresa) or {})
        clave = (clave_aplicacion or "").replace(" ", "")
        if clave:
            actual["clave"] = self._cifrador.cifrar(clave)
        elif not actual.get("clave"):
            raise ValueError("Falta la contraseña de aplicación.")
        if actual.get("casilla") != casilla:
            actual["ultima_lectura"] = None  # otra casilla: se vuelve a traer el último mes
        actual.update(casilla=casilla, actualizado_por=actor, actualizado_en=datetime.now(UTC))
        self._parametros[empresa] = actual
        return self.ver(empresa)

    def _bandeja(self, empresa: str) -> tuple[dict[str, Any], BandejaConPrueba]:
        datos = self._parametros.get(empresa) or {}
        if not datos.get("casilla") or not datos.get("clave"):
            raise ValueError("Primero cargá la casilla y la contraseña de aplicación.")
        clave = self._cifrador.descifrar(datos["clave"])
        return datos, self._crear_bandeja(datos["casilla"], clave, datos.get("ultima_lectura"))

    def probar(self, empresa: str) -> None:
        self._bandeja(self._empresa(empresa))[1].probar()

    def leer(self, empresa: str) -> ResultadoLectura:
        empresa = self._empresa(empresa)
        datos, bandeja = self._bandeja(empresa)
        ahora = datetime.now(UTC)
        try:
            documentos = bandeja.listar_nuevos()
        except Exception as exc:
            resultado = ResultadoLectura(empresa, ahora, 0, 0, 0, str(exc))
            self._parametros[empresa] = {**datos, "ultimo_resultado": asdict(resultado)}
            raise
        incorporados = self._ingestar.ejecutar(_FuenteFija(bandeja.estado, documentos))
        for original in incorporados:
            self._extraer.ejecutar(original.id)
        completa = getattr(bandeja, "completa", True)
        resultado = ResultadoLectura(empresa, ahora, len(documentos), len(incorporados),
                                     len(documentos) - len(incorporados), incompleta=not completa)
        # La última lectura sólo avanza cuando Gmail respondió, y si la lectura quedó cortada
        # avanza hasta el último correo procesado: así nunca se saltean correos.
        hasta = ahora if completa else (getattr(bandeja, "leido_hasta", None) or datos.get("ultima_lectura"))
        self._parametros[empresa] = {**datos, "ultima_lectura": hasta, "ultimo_resultado": asdict(resultado)}
        return resultado

    def leer_todas(self) -> list[ResultadoLectura]:
        resultados = []
        for empresa in EMPRESAS:
            datos = self._parametros.get(empresa) or {}
            if not datos.get("casilla") or not datos.get("clave"):
                continue
            try:
                resultados.append(self.leer(empresa))
            except Exception as exc:  # una casilla caída no frena a la otra
                resultados.append(ResultadoLectura(empresa, datetime.now(UTC), 0, 0, 0, str(exc)))
        return resultados


class _FuenteFija:
    def __init__(self, estado: str, documentos: list) -> None:
        self.estado = estado
        self._documentos = documentos

    def listar_nuevos(self):
        return self._documentos
