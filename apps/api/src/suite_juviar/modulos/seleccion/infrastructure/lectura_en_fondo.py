"""Cola de lectura de CV en segundo plano, dentro del proceso de la API.

Un solo hilo por base de datos lee los CV de a uno (reglas + OCR y después IA), así la ingesta del
correo, del WhatsApp o de la carga manual no espera a la IA. El hilo arranca cuando hay trabajo y
termina cuando la cola queda vacía.

Un reintento no duerme dentro del hilo: el CV vuelve a la cola con la hora a partir de la cual se
puede leer, y mientras tanto el hilo sigue con los demás.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from ..application.datos_cv import EN_COLA, LEYENDO, REINTENTO

_registro = logging.getLogger(__name__)


@dataclass
class _Pendiente:
    releer_reglas: bool = False
    intento: int = 0
    vence: float = 0.0  # reloj monotónico: antes de esto no se lee


class ColaLecturaCV:
    def __init__(self, procesar: Callable[..., object], reloj: Callable[[], float] = time.monotonic) -> None:
        self._procesar = procesar
        self._reloj = reloj
        self._pendientes: dict[str, _Pendiente] = {}
        self._actual: str | None = None
        self._hechos = 0
        self._lote = 0
        self._bloqueo = threading.Lock()
        self._aviso = threading.Condition(self._bloqueo)
        self._vacia = threading.Event()
        self._vacia.set()
        self._hilo: threading.Thread | None = None

    def encolar(self, cv_id: str, *, releer_reglas: bool = False) -> bool:
        """True si quedó en la cola; False si ya estaba esperando o leyéndose."""
        with self._bloqueo:
            if cv_id == self._actual or cv_id in self._pendientes:
                if releer_reglas and cv_id in self._pendientes:
                    self._pendientes[cv_id].releer_reglas = True
                return False
            if not self._pendientes and self._actual is None:
                self._hechos = self._lote = 0
            self._pendientes[cv_id] = _Pendiente(releer_reglas)
            self._lote += 1
            self._despertar()
        return True

    def estado(self, cv_id: str) -> str | None:
        with self._bloqueo:
            if cv_id == self._actual:
                return LEYENDO
            pendiente = self._pendientes.get(cv_id)
            if pendiente is None:
                return None
            return REINTENTO if pendiente.vence > self._reloj() else EN_COLA

    def progreso(self) -> dict[str, int]:
        with self._bloqueo:
            ahora = self._reloj()
            return {"en_cola": len(self._pendientes) + (1 if self._actual else 0),
                    "en_espera": sum(1 for p in self._pendientes.values() if p.vence > ahora),
                    "hechos": self._hechos, "lote": self._lote}

    def esperar(self, segundos: float = 30) -> bool:
        return self._vacia.wait(segundos)

    def _despertar(self) -> None:
        """Con el bloqueo tomado: hay trabajo nuevo."""
        self._vacia.clear()
        if self._hilo is None:
            self._hilo = threading.Thread(target=self._trabajar, name="lectura-cv-seleccion", daemon=True)
            self._hilo.start()
        self._aviso.notify()

    def _siguiente(self) -> tuple[str, _Pendiente] | None:
        """Con el bloqueo tomado: el primer CV que ya se puede leer; si todos esperan, espera."""
        while self._pendientes:
            ahora = self._reloj()
            for cv_id, pendiente in self._pendientes.items():
                if pendiente.vence <= ahora:
                    return cv_id, self._pendientes.pop(cv_id)
            self._aviso.wait(min(p.vence for p in self._pendientes.values()) - ahora)
        return None

    def _trabajar(self) -> None:
        while True:
            with self._bloqueo:
                siguiente = self._siguiente()
                if siguiente is None:
                    self._actual = None
                    self._hilo = None
                    self._vacia.set()
                    return
                cv_id, pendiente = siguiente
                self._actual = cv_id
            reintento = None
            try:
                reintento = self._procesar(cv_id, releer_reglas=pendiente.releer_reglas,
                                           intento=pendiente.intento)
            except Exception:  # noqa: BLE001 - un CV que falla no frena a los demás
                _registro.exception("No se pudo leer el CV %s en segundo plano", cv_id[:12])
            with self._bloqueo:
                self._actual = None
                segundos = getattr(reintento, "segundos", None)
                if segundos is not None and cv_id not in self._pendientes:
                    # Vuelve a la cola con hora de vencimiento; el hilo sigue con los demás.
                    self._pendientes[cv_id] = _Pendiente(False, getattr(reintento, "intento", 0),
                                                         self._reloj() + segundos)
                else:
                    self._hechos += 1


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
