"""Única costura HTTP entre identidad y autorización."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, status

from ..application.ingreso import ServicioIngreso
from ..application.recuperacion import ServicioRecuperacion
from ..application.subida_pin import ServicioSubidaPin
from ..domain.sesion import Sesion
from ..domain.subida_pin import PERMISO_SUBIDA

DUENO_CATALOGO_PERMISOS = "RRHH junto con Sistemas"

PERMISOS_POR_PERFIL: dict[str, frozenset[str]] = {
    "DEPOSITO": frozenset({
        "suite.acceder", "epp.entrega.operar", "epp.entrega.leer",
        "epp.catalogo.leer", "epp.stock.leer", "epp.stock.editar",
    }),
    "CAMPO": frozenset({"suite.acceder", "recepcion.romaneo.crear"}),
    "BASCULA": frozenset({
        "suite.acceder", "recepcion.romaneo.crear", "fila.tablero.leer", "fila.organica.operar",
        "mosto.leer", "mosto.viajes.ingresar",
    }),
    "BODEGA": frozenset({
        "suite.acceder", "fila.contactos.gestionar", "fila.tablero.leer", "fila.turnos.gestionar", "bot.simulador.usar",
        "bot.conversaciones.leer",
    }),
    "RRHH": frozenset({
        "suite.acceder", "epp.catalogo.leer", "epp.entrega.leer", "epp.stock.leer",
        "seleccion.gestionar", "capacitacion.gestionar", "legajo.leer", "legajo.adjuntos.gestionar",
        "turnos.cronograma.leer", "turnos.imputacion.aprobar",
        # Lo que el personal manda por WhatsApp (certificados, EPP) y recorridos del micro.
        "rrhh.bandeja.gestionar", "rrhh.micro.gestionar",
    }),
    "MEDICO": frozenset({
        "suite.acceder", "salud.diagnostico.leer", "salud.certificado.gestionar",
        "salud.persona.buscar",
    }),
    "HYS": frozenset({
        "suite.acceder", "epp.catalogo.leer", "epp.catalogo.editar",
        "epp.matriz.editar", "epp.stock.leer", "epp.entrega.leer",
        "epp.analitica.leer", "capacitacion.gestionar",
    }),
    "COMPRAS": frozenset({"suite.acceder", "epp.catalogo.leer", "epp.stock.leer", "epp.stock.editar", "epp.aviso.gestionar", "epp.analitica.leer",
                         "mosto.leer", "mosto.compras.gestionar", "controles_fiscales.operar"}),
    "SUPERVISOR": frozenset({"suite.acceder", "capacitacion.leer", "turnos.cronograma.leer", "turnos.cronograma.editar"}),
    "MANTENIMIENTO": frozenset({"suite.acceder", "activos.gestionar"}),
    # Sólo el Encargado autoriza (firma) los remitos de salida de equipos y herramientas.
    "ENCARGADO_MANTENIMIENTO": frozenset({"suite.acceder", "activos.gestionar", "activos.remitos.firmar"}),
    # Mosto: Laboratorio analiza y decide por Calidad; el Jefe de Producción puede aprobar lo
    # que rechazó Calidad y registra descargas; Comercial decide con escasez y cierra contratos.
    "LABORATORIO": frozenset({"suite.acceder", "mosto.leer", "mosto.laboratorio"}),
    "PRODUCCION": frozenset({"suite.acceder", "mosto.leer", "mosto.produccion"}),
    "COMERCIAL": frozenset({"suite.acceder", "mosto.leer", "mosto.compras.gestionar", "mosto.comercial"}),
    # Controles fiscales de ARCA sobre las facturas de proveedores.
    "ADMINISTRACION": frozenset({"suite.acceder", "controles_fiscales.operar"}),
}
PERMISOS_POR_PERFIL["SUPERADMIN"] = frozenset().union(
    *PERMISOS_POR_PERFIL.values(), {"identidad.usuarios.gestionar", "bot.personal.gestionar", "parametros.gestionar"}
)

PERFIL_LEGAJO_SIMULADO = {"1210": "DEPOSITO", "1501": "CAMPO", "1601": "BASCULA"}


COOKIE_SESION = "sj_sesion"
# Link personal + PIN para subir facturas desde el celular (pantalla /subir). Es otra cookie y
# sólo se mira cuando la pantalla lo pide con la cabecera: el ingreso normal no cambia.
COOKIE_SUBIDA = "sj_subida"
CABECERA_SUBIDA = "X-Ingreso-Subida"
_ingreso: ServicioIngreso | None = None
_subida: ServicioSubidaPin | None = None
_recuperacion: ServicioRecuperacion | None = None
# Envío de correos internos (casilla de RRHH de Parámetros). Lo conecta la composición:
# identidad no conoce el módulo de selección.
_envio_correo: Callable[[str, str, str], bool] | None = None


def configurar_ingreso(servicio: ServicioIngreso | None) -> None:
    global _ingreso
    _ingreso = servicio


def servicio_ingreso() -> ServicioIngreso:
    if _ingreso is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "El ingreso no está configurado.")
    return _ingreso


def configurar_subida(servicio: ServicioSubidaPin | None) -> None:
    global _subida
    _subida = servicio


def servicio_subida() -> ServicioSubidaPin:
    if _subida is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "El ingreso con PIN no está configurado.")
    return _subida


def configurar_recuperacion(servicio: ServicioRecuperacion | None) -> None:
    global _recuperacion
    _recuperacion = servicio


def servicio_recuperacion() -> ServicioRecuperacion:
    if _recuperacion is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "El ingreso no está configurado.")
    return _recuperacion


def configurar_envio_correo(enviar: Callable[[str, str, str], bool] | None) -> None:
    global _envio_correo
    _envio_correo = enviar


def enviar_correo_interno(destino: str, asunto: str, cuerpo: str) -> bool:
    """False si todavía no hay con qué mandar (ninguna casilla de RRHH cargada)."""
    return bool(_envio_correo and _envio_correo(destino, asunto, cuerpo))


def sesion_de_subida(token: str | None) -> Sesion:
    persona = servicio_subida().resolver(token) if token else None
    if persona is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta ingresar con el PIN.")
    return Sesion(
        actor=persona.actor, empresa=persona.empresas[0], permisos=frozenset({PERMISO_SUBIDA}),
        identidad_simulada=False, subida_pin=True, empresas=persona.empresas,
    )


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
    token: Annotated[str | None, Cookie(alias=COOKIE_SESION)] = None,
    subida: Annotated[str | None, Header(alias=CABECERA_SUBIDA)] = None,
    token_subida: Annotated[str | None, Cookie(alias=COOKIE_SUBIDA)] = None,
) -> Sesion:
    """Con identidad real, la sesión sale de la cookie de ingreso; las cabeceras se ignoran.

    La pantalla /subir pide la sesión de PIN con su cabecera: entonces sólo vale esa cookie,
    que tiene un único permiso (``controles_fiscales.subir_celular``).
    """
    if subida:
        return sesion_de_subida(token_subida)
    if not identidad_es_simulada():
        resuelto = servicio_ingreso().resolver(token) if token else None
        if resuelto is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta una sesión autenticada.")
        usuario, guardada = resuelto
        if usuario.debe_cambiar_clave:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Antes de seguir, cambiá tu contraseña.")
        return Sesion(
            actor=usuario.email,
            empresa=guardada.empresa,
            permisos=PERMISOS_POR_PERFIL.get(usuario.perfil, frozenset()),
            identidad_simulada=False,
        )
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


def exigir_alguno(*permisos: str) -> Callable[..., Sesion]:
    """Pasa con cualquiera de los permisos (p. ej. operar en Gestión o subir con PIN)."""

    def dependencia(sesion: SesionActual) -> Sesion:
        if not any(sesion.puede(p) for p in permisos):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"La sesión no tiene el permiso requerido: {' o '.join(permisos)}.",
            )
        return sesion

    dependencia.permiso_requerido = "|".join(permisos)  # type: ignore[attr-defined]
    dependencia.__name__ = "exigir_" + "_o_".join(p.replace(".", "_") for p in permisos)
    return dependencia
