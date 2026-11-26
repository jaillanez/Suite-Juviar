"""Lectura de cada CV con IA al entrar, con reintentos acotados, y relectura de los ya cargados.

La IA sólo corre si el servidor la tiene autorizada (la misma autorización que «leer con IA» a pedido),
y eso se mira en el momento de cada lectura. Si la IA no está o falla, el CV queda con lo que leyeron
las reglas (texto del PDF u OCR) y el error queda registrado para volver a intentarlo.

Los reintentos no frenan la cola: «procesar» no duerme, devuelve cuándo volver a intentar y la cola
lo reencola con esa hora. Si la IA falla varias veces seguidas (cualquier CV), se pausa unos minutos:
los CV que esperan quedan «IA no disponible, se reintenta más tarde» sin perderse.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..domain.modelos import CVOriginal
from ..domain.puertos import RepositorioCVOriginales, RepositorioExtracciones
from .datos_cv import ERROR, LEIDO, NO_DISPONIBLE, SIN_LEER, VERSION_FICHA, valores_de_ficha
from .datos_faltantes import OBLIGATORIOS
from .extraccion import SIN_TEXTO, ExtraerDatosCV

_registro = logging.getLogger(__name__)
ESPERAS_REINTENTO = (10.0, 60.0)  # tres intentos en total por CV
FALLAS_PARA_PAUSAR = 5  # fallas seguidas de la IA (en cualquier CV) que pausan la lectura
PAUSA_IA = 300.0  # segundos que la IA queda en pausa después de esas fallas
LECTURA_AUTOMATICA = "lectura automática"
IA_EN_PAUSA = "IA no disponible, se reintenta más tarde."


@dataclass(frozen=True)
class Reintento:
    """Volver a intentar este CV dentro de «segundos», como intento número «intento» (0 es el primero)."""
    segundos: float
    intento: int


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
        esperas: tuple[float, ...] | None = None,
        reloj: Callable[[], float] = time.monotonic,
        fallas_para_pausar: int = FALLAS_PARA_PAUSAR,
        pausa: float = PAUSA_IA,
    ) -> None:
        self._originales = originales
        self._extracciones = extracciones
        self._extraer = extraer
        self._fichas = fichas
        self._errores = errores
        self._leer = leer
        self._permitida = permitida  # se evalúa en cada lectura, nunca queda guardada
        self._esperas = ESPERAS_REINTENTO if esperas is None else esperas
        self._reloj = reloj
        self._fallas_para_pausar = fallas_para_pausar
        self._pausa = pausa
        self._fallas_seguidas = 0
        self._pausada_hasta = 0.0

    def permitida(self) -> bool:
        return self._permitida()

    def en_pausa(self) -> float:
        """Segundos que le faltan a la pausa de la IA (0 si no está en pausa)."""
        return max(0.0, self._pausada_hasta - self._reloj())

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

    def procesar(self, cv_id: str, *, releer_reglas: bool = False, intento: int = 0) -> Reintento | None:
        """Trabajo en segundo plano: reglas (si hace falta) y luego un intento con IA.

        No duerme nunca: si hay que volver a intentar, devuelve cuándo y la cola lo reencola."""
        original = self._originales.obtener_original(cv_id)
        if original is None:
            return None
        if releer_reglas or self._extracciones.obtener_extraccion(cv_id) is None:
            self._extraer.ejecutar(cv_id, conservar_anteriores=True)
        if not self.necesita_ia(cv_id, incluir_errores=True):  # autorización mirada ahora
            return None
        if pausa := self.en_pausa():
            self._anotar(cv_id, IA_EN_PAUSA, intento, en_pausa=True)
            return Reintento(pausa, intento)
        try:
            self._guardar(cv_id, self._leer(original), LECTURA_AUTOMATICA)
        except ValueError as exc:  # el archivo no se puede mandar: reintentar no sirve
            self._anotar(cv_id, str(exc), intento + 1)
            return None
        except RuntimeError as exc:
            _registro.warning("Lectura con IA del CV %s, intento %s: %s", cv_id[:12], intento + 1, exc)
            return self._fallo(cv_id, str(exc), intento)
        self._fallas_seguidas = 0
        return None

    def _fallo(self, cv_id: str, error: str, intento: int) -> Reintento | None:
        self._fallas_seguidas += 1
        if self._fallas_seguidas >= self._fallas_para_pausar:
            self._fallas_seguidas = 0
            self._pausada_hasta = self._reloj() + self._pausa
            _registro.warning("La IA falló %s veces seguidas: lectura en pausa %s s",
                              self._fallas_para_pausar, int(self._pausa))
        if intento < len(self._esperas):
            espera = max(self._esperas[intento], self.en_pausa())
            self._anotar(cv_id, error if not self.en_pausa() else IA_EN_PAUSA, intento + 1,
                         en_pausa=bool(self.en_pausa()))
            return Reintento(espera, intento + 1)
        self._anotar(cv_id, error, intento + 1)
        return None

    def _anotar(self, cv_id: str, error: str, intentos: int, *, en_pausa: bool = False) -> None:
        self._errores[cv_id] = {"error": error, "intentos": intentos, "en": datetime.now(UTC).isoformat(),
                                **({"en_pausa": True} if en_pausa else {})}

    def _guardar(self, cv_id: str, ficha: dict[str, Any], actor: str) -> dict[str, Any]:
        ficha = {**ficha, "leido_por": actor, "leido_en": datetime.now(UTC).isoformat(),
                 "version_lectura": VERSION_FICHA}
        self._fichas[cv_id] = ficha
        self._errores.pop(cv_id, None)
        return ficha
