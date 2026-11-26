"""Cola de lectura de CV en segundo plano, dentro del proceso de la API.

Un solo hilo por base de datos lee los CV de a uno (reglas + OCR y después IA), así la ingesta del
correo, del WhatsApp o de la carga manual no espera a la IA. El hilo arranca cuando hay trabajo y
termina cuando la cola queda vacía.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from ..application.datos_cv import EN_COLA, LEYENDO

_registro = logging.getLogger(__name__)


class ColaLecturaCV:
    def __init__(self, procesar: Callable[..., None]) -> None:
        self._procesar = procesar
        self._pendientes: dict[str, bool] = {}  # cv_id → volver a leer con reglas
        self._actual: str | None = None
        self._hechos = 0
        self._lote = 0
        self._bloqueo = threading.Lock()
        self._vacia = threading.Event()
        self._vacia.set()
        self._hilo: threading.Thread | None = None

    def encolar(self, cv_id: str, *, releer_reglas: bool = False) -> bool:
        """True si quedó en la cola; False si ya estaba esperando o leyéndose."""
        with self._bloqueo:
            if cv_id == self._actual or cv_id in self._pendientes:
                if releer_reglas and cv_id in self._pendientes:
                    self._pendientes[cv_id] = True
                return False
            if not self._pendientes and self._actual is None:
                self._hechos = self._lote = 0
            self._pendientes[cv_id] = releer_reglas
            self._lote += 1
            self._vacia.clear()
            if self._hilo is None:
                self._hilo = threading.Thread(target=self._trabajar, name="lectura-cv-seleccion", daemon=True)
                self._hilo.start()
        return True

    def estado(self, cv_id: str) -> str | None:
        with self._bloqueo:
            if cv_id == self._actual:
                return LEYENDO
            return EN_COLA if cv_id in self._pendientes else None

    def progreso(self) -> dict[str, int]:
        with self._bloqueo:
            return {"en_cola": len(self._pendientes) + (1 if self._actual else 0),
                    "hechos": self._hechos, "lote": self._lote}

    def esperar(self, segundos: float = 30) -> bool:
        return self._vacia.wait(segundos)

    def _trabajar(self) -> None:
        while True:
            with self._bloqueo:
                if not self._pendientes:
                    self._actual = None
                    self._hilo = None
                    self._vacia.set()
                    return
                cv_id = next(iter(self._pendientes))
                releer = self._pendientes.pop(cv_id)
                self._actual = cv_id
            try:
                self._procesar(cv_id, releer_reglas=releer)
            except Exception:  # noqa: BLE001 - un CV que falla no frena a los demás
                _registro.exception("No se pudo leer el CV %s en segundo plano", cv_id[:12])
            with self._bloqueo:
                self._hechos += 1
                self._actual = None


_COLAS: dict[str, tuple[object, ColaLecturaCV]] = {}
_BLOQUEO = threading.Lock()


def compartida[T](clave: str, crear: Callable[[], tuple[T, ColaLecturaCV]]) -> tuple[T, ColaLecturaCV]:
    """El mismo servicio y la misma cola para todos los caminos de ingesta de una base de datos."""
    with _BLOQUEO:
        if clave not in _COLAS:
            _COLAS[clave] = crear()
        return _COLAS[clave]  # type: ignore[return-value]


def esperar_todas(segundos: float = 30) -> bool:
    """Para las pruebas: espera a que todas las colas terminen."""
    return all(cola.esperar(segundos) for _, cola in list(_COLAS.values()))
