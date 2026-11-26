"""Lectura de cada CV con IA al entrar, con reintentos acotados, y relectura de los ya cargados.

La IA sólo corre si el servidor la tiene autorizada (la misma autorización que «leer con IA» a pedido).
Si la IA no está o falla, el CV queda con lo que leyeron las reglas (texto del PDF u OCR) y el error
queda registrado para volver a intentarlo.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, MutableMapping
from datetime import UTC, datetime
from typing import Any

from ..domain.modelos import CVOriginal
from ..domain.puertos import RepositorioCVOriginales, RepositorioExtracciones
from .datos_cv import ERROR, LEIDO, NO_DISPONIBLE, SIN_LEER, VERSION_FICHA, valores_de_ficha
from .datos_faltantes import OBLIGATORIOS
from .extraccion import SIN_TEXTO, ExtraerDatosCV

_registro = logging.getLogger(__name__)
ESPERAS_REINTENTO = (10.0, 60.0)  # tres intentos en total por CV
LECTURA_AUTOMATICA = "lectura automática"


class LeerCVsConIA:
    def __init__(
        self,
        originales: RepositorioCVOriginales,
        extracciones: RepositorioExtracciones,
        extraer: ExtraerDatosCV,
        fichas: MutableMapping[str, dict[str, Any]],
        errores: MutableMapping[str, dict[str, Any]],
        leer: Callable[[CVOriginal], dict[str, Any]],
        permitida: Callable[[], bool],
        dormir: Callable[[float], None],
        esperas: tuple[float, ...] | None = None,
    ) -> None:
        self._originales = originales
        self._extracciones = extracciones
        self._extraer = extraer
        self._fichas = fichas
        self._errores = errores
        self._leer = leer
        self._permitida = permitida
        self._dormir = dormir
        self._esperas = ESPERAS_REINTENTO if esperas is None else esperas

    def permitida(self) -> bool:
        return self._permitida()

    def estado(self, cv_id: str) -> str:
        if cv_id in self._fichas:
            return LEIDO
        if not self._permitida():
            return NO_DISPONIBLE
        return ERROR if cv_id in self._errores else SIN_LEER

    def error(self, cv_id: str) -> dict[str, Any] | None:
        return self._errores.get(cv_id)

    def necesita_ia(self, cv_id: str, *, incluir_errores: bool = False) -> bool:
        """Sin ficha, o con una ficha vieja a la que le falta algún dato obligatorio."""
        if not self._permitida() or (cv_id in self._errores and not incluir_errores):
            return False
        ficha = self._fichas.get(cv_id)
        if ficha is None:
            return True
        if (ficha.get("version_lectura") or 1) >= VERSION_FICHA:
            return False
        return any(c not in valores_de_ficha(ficha) for c in OBLIGATORIOS)

    def necesita_reglas(self, cv_id: str) -> bool:
        extraccion = self._extracciones.obtener_extraccion(cv_id)
        return extraccion is None or extraccion.estado == SIN_TEXTO or bool(extraccion.campos_pendientes)

    def leer_ahora(self, cv_id: str, actor: str) -> dict[str, Any]:
        """Un intento, a pedido de una persona: el error vuelve a quien lo pidió."""
        original = self._originales.obtener_original(cv_id)
        if original is None:
            raise LookupError(cv_id)
        return self._guardar(cv_id, self._leer(original), actor)

    def procesar(self, cv_id: str, *, releer_reglas: bool = False) -> None:
        """Trabajo en segundo plano: reglas (si hace falta) y luego IA con reintentos acotados."""
        original = self._originales.obtener_original(cv_id)
        if original is None:
            return
        if releer_reglas or self._extracciones.obtener_extraccion(cv_id) is None:
            self._extraer.ejecutar(cv_id, conservar_anteriores=True)
        if not self.necesita_ia(cv_id, incluir_errores=True):
            return
        ultimo = ""
        for intento in range(len(self._esperas) + 1):
            try:
                self._guardar(cv_id, self._leer(original), LECTURA_AUTOMATICA)
                return
            except RuntimeError as exc:
                ultimo = str(exc)
                _registro.warning("Lectura con IA del CV %s, intento %s: %s", cv_id[:12], intento + 1, exc)
                if intento < len(self._esperas):
                    self._dormir(self._esperas[intento])
        self._errores[cv_id] = {"error": ultimo, "intentos": len(self._esperas) + 1,
                                "en": datetime.now(UTC).isoformat()}

    def _guardar(self, cv_id: str, ficha: dict[str, Any], actor: str) -> dict[str, Any]:
        ficha = {**ficha, "leido_por": actor, "leido_en": datetime.now(UTC).isoformat(),
                 "version_lectura": VERSION_FICHA}
        self._fichas[cv_id] = ficha
        self._errores.pop(cv_id, None)
        return ficha
