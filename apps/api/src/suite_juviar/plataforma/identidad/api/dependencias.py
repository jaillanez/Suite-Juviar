"""Única costura HTTP entre identidad y autorización."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from ..domain.sesion import Sesion

DUENO_CATALOGO_PERMISOS = "RRHH junto con Sistemas"

PERMISOS_POR_PERFIL: dict[str, frozenset[str]] = {
    "DEPOSITO": frozenset({
        "suite.acceder", "epp.entrega.operar", "epp.entrega.leer",
        "epp.catalogo.leer", "epp.stock.leer", "epp.stock.editar",
    }),
    "CAMPO": frozenset({"suite.acceder", "recepcion.romaneo.crear"}),
    "BASCULA": frozenset({"suite.acceder", "recepcion.romaneo.crear"}),
    "RRHH": frozenset({
        "suite.acceder", "epp.catalogo.leer", "epp.entrega.leer", "epp.stock.leer",
        "seleccion.gestionar", "capacitacion.gestionar", "legajo.leer",
        "turnos.cronograma.leer", "turnos.imputacion.aprobar",
    }),
    "MEDICO": frozenset({"suite.acceder", "salud.diagnostico.leer", "salud.certificado.gestionar"}),
    "HYS": frozenset({
        "suite.acceder", "epp.catalogo.leer", "epp.catalogo.editar",
        "epp.matriz.editar", "epp.stock.leer", "epp.entrega.leer",
        "epp.analitica.leer", "capacitacion.gestionar",
    }),
    "COMPRAS": frozenset({"suite.acceder", "epp.catalogo.leer", "epp.stock.leer", "epp.stock.editar", "epp.aviso.gestionar", "epp.analitica.leer"}),
    "SUPERVISOR": frozenset({"suite.acceder", "capacitacion.leer", "turnos.cronograma.leer", "turnos.cronograma.editar"}),
}

PERFIL_LEGAJO_SIMULADO = {"1210": "DEPOSITO", "1501": "CAMPO", "1601": "BASCULA"}


def identidad_es_simulada() -> bool:
    return os.getenv("SJ_IDENTIDAD_REAL", "").lower() not in {"1", "true", "si"}


def exigir_identidad_configurada(entorno: str) -> None:
    if entorno.lower() in {"produccion", "production", "prod"} and identidad_es_simulada():
        raise RuntimeError("La API no arranca en producción con identidad simulada.")


def resolver_sesion(
    perfil: Annotated[str | None, Header(alias="X-Perfil-Simulado")] = None,
    actor: Annotated[str | None, Header(alias="X-Actor-Simulado")] = None,
    empresa: Annotated[str, Header(alias="X-Empresa-Simulada")] = "ENAV",
    legajo_declarado: Annotated[str | None, Header(alias="X-Legajo-Usuario")] = None,
) -> Sesion:
    """Será el único cuerpo reemplazado al conectar el autenticador real."""
    if not identidad_es_simulada():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta una sesión autenticada.")
    perfil_resuelto = (
        perfil
        or PERFIL_LEGAJO_SIMULADO.get(legajo_declarado or "")
        or ("DEPOSITO" if legajo_declarado else "")
    ).upper()
    if not perfil_resuelto or perfil_resuelto not in PERMISOS_POR_PERFIL:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta una sesión válida.")
    return Sesion(
        actor=actor or legajo_declarado or f"{perfil_resuelto.lower()}-prueba",
        empresa=empresa.upper(),
        permisos=PERMISOS_POR_PERFIL[perfil_resuelto],
        identidad_simulada=True,
    )


SesionActual = Annotated[Sesion, Depends(resolver_sesion)]


def exigir_permiso(permiso: str) -> Callable[..., Sesion]:
    def dependencia(sesion: SesionActual) -> Sesion:
        if not sesion.puede(permiso):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"La sesión no tiene el permiso requerido: {permiso}.",
            )
        return sesion

    dependencia.permiso_requerido = permiso  # type: ignore[attr-defined]
    dependencia.__name__ = f"exigir_{permiso.replace('.', '_')}"
    return dependencia
