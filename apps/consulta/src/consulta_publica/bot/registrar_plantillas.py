"""Envía a revisión de Meta las plantillas del catálogo que todavía no están en la cuenta.

Uso (con META_TOKEN y META_CUENTA_ID cargadas, por ejemplo desde /etc/suite/bot.env):

    python -m consulta_publica.bot.registrar_plantillas            # crea las que faltan
    python -m consulta_publica.bot.registrar_plantillas --listar   # sólo muestra el estado

Las que ya existen (en cualquier estado) no se tocan: se puede correr las veces que haga falta.
Meta revisa cada plantilla nueva; el estado pasa de PENDING a APPROVED o REJECTED.
"""

from __future__ import annotations

import os
import sys

from .meta_cloud import ClienteMeta, ConfigMeta, ErrorMeta
from .plantillas import CATALOGO


def _cliente() -> ClienteMeta:
    token = os.environ.get("META_TOKEN", "").strip()
    cuenta = os.environ.get("META_CUENTA_ID", "").strip()
    if not token or not cuenta:
        raise RuntimeError("Faltan las variables de entorno META_TOKEN y META_CUENTA_ID")
    version = os.environ.get("META_VERSION", "").strip() or "v23.0"
    return ClienteMeta(ConfigMeta(token=token, numero_id="", version=version, cuenta_id=cuenta))


def _estado(existentes: list[dict], idioma: str) -> str | None:
    for plantilla in existentes:
        if plantilla.get("language") == idioma:
            motivo = plantilla.get("rejected_reason")
            estado = str(plantilla.get("status") or "?")
            return f"{estado} ({motivo})" if motivo and motivo != "NONE" else estado
    return None


def registrar(cliente: ClienteMeta, listar: bool = False, salida=print) -> int:
    """Devuelve cuántas plantillas no se pudieron crear (0 si salió todo bien)."""
    fallas = 0
    for plantilla in CATALOGO.values():
        try:
            estado = _estado(cliente.plantillas(plantilla.nombre), plantilla.idioma)
        except ErrorMeta as exc:
            salida(f"{plantilla.nombre}: no se pudo consultar ({exc})")
            fallas += 1
            continue
        if estado is not None or listar:
            salida(f"{plantilla.nombre}: {estado or 'no está en la cuenta'}")
            continue
        try:
            respuesta = cliente.crear_plantilla(plantilla.para_registrar())
        except ErrorMeta as exc:
            salida(f"{plantilla.nombre}: Meta no la aceptó ({exc})")
            fallas += 1
            continue
        salida(f"{plantilla.nombre}: enviada a revisión, {respuesta.get('status') or 'PENDING'}")
    return fallas


def main(argumentos: list[str]) -> int:
    if any(a not in {"--listar"} for a in argumentos[1:]):
        print("uso: python -m consulta_publica.bot.registrar_plantillas [--listar]")
        return 2
    return 1 if registrar(_cliente(), listar="--listar" in argumentos) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
