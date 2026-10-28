"""Diálogo del bot. Función pura: no sabe de WhatsApp ni de bases.

Reproduce el recorrido que el productor ya conoce —cuenta, estadísticas o
reporte, período— y agrega la gestión de contactos. Guarda dónde quedó cada
teléfono para que "Últimos 3 meses" se entienda después de "Ver estadísticas".
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import date

from .periodos import Periodo, cosecha_de, interpretar

MENU, PERIODO, CUENTA = "menu", "periodo", "cuenta"
ESTADISTICAS, REPORTE, CONTACTOS = "estadisticas", "reporte", "contactos"

NO_REGISTRADO = (
    "Este número no está registrado para consultar entregas.\n"
    "Pedile a la bodega que lo dé de alta, o a alguien que ya esté registrado "
    "que te invite."
)
SIN_PERMISO_INFORMES = (
    "Este número puede pedir turnos, pero no ver entregas.\n"
    "Si necesitás los informes, pedíselo a quien administra los contactos."
)
CADUCADO = "Pasó un rato desde tu última consulta. Empecemos de nuevo."
MINUTOS_SESION = 30


@dataclass(frozen=True)
class Cuenta:
    clientecuit: str
    codigo: str
    titular: str

    def como_opcion(self) -> str:
        return f"{self.titular.strip().rstrip('.')} ({self.codigo})"


@dataclass(frozen=True)
class Estado:
    paso: str = MENU
    cuenta: str | None = None      # clientecuit elegido
    pedido: str | None = None      # estadisticas | reporte


@dataclass
class Respuesta:
    texto: str
    opciones: list[str] = field(default_factory=list)
    estado: Estado = field(default_factory=Estado)
    accion: str | None = None              # estadisticas | reporte
    periodo: Periodo | None = None
    cuenta: Cuenta | None = None

    def con_botones(self) -> str:
        if not self.opciones:
            return self.texto
        lineas = "\n".join(f"{i} — {o}" for i, o in enumerate(self.opciones, start=1))
        return f"{self.texto}\n\n{lineas}"


def _normalizar(texto: str | None) -> str:
    limpio = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    return "".join(c for c in limpio if not unicodedata.combining(c))


def _menu(cuenta: Cuenta, varias: bool) -> Respuesta:
    opciones = ["Ver estadísticas", "Descargar reporte", "Mis contactos"]
    if varias:
        opciones.append("Cambiar de cuenta")
    return Respuesta(
        texto=f"{cuenta.titular.strip().rstrip('.')} — Cuenta {cuenta.codigo}\n¿Qué querés consultar?",
        opciones=opciones,
        estado=Estado(MENU, cuenta.clientecuit),
    )


def _pedir_cuenta(cuentas: list[Cuenta]) -> Respuesta:
    return Respuesta(
        texto="Tenés más de una cuenta. ¿Cuál querés consultar?",
        opciones=[c.como_opcion() for c in cuentas],
        estado=Estado(CUENTA),
    )


def _pedir_periodo(estado: Estado, hoy: date, aviso: str = "") -> Respuesta:
    texto = "¿De qué período?" if not aviso else aviso + "\n¿De qué período?"
    return Respuesta(
        texto=texto + '\nTambién podés escribirlo: "marzo 2026", "este año", "últimos 6 meses".',
        opciones=[f"Cosecha {cosecha_de(hoy)}", "Últimos 3 meses"],
        estado=Estado(PERIODO, estado.cuenta, estado.pedido),
    )


def responder(
    texto: str | None,
    cuentas: list[Cuenta],
    estado: Estado,
    hoy: date,
    puede_ver_informes: bool = True,
    puede_administrar: bool = False,
) -> Respuesta:
    if not cuentas:
        return Respuesta(NO_REGISTRADO)
    if not puede_ver_informes:
        return Respuesta(SIN_PERMISO_INFORMES)

    t = _normalizar(texto)
    elegida = next((c for c in cuentas if c.clientecuit == estado.cuenta), None)

    # Volver o empezar de nuevo, desde cualquier paso.
    if t in {"volver", "menu", "menú", "0", "hola", "buenas", "buen dia", "buenas tardes"}:
        if elegida or len(cuentas) == 1:
            return _menu(elegida or cuentas[0], len(cuentas) > 1)
        return _pedir_cuenta(cuentas)

    if estado.paso == CUENTA or elegida is None:
        if len(cuentas) == 1:
            elegida = cuentas[0]
        else:
            indice = _opcion_elegida(t, [c.como_opcion() for c in cuentas])
            if indice is None:
                return _pedir_cuenta(cuentas)
            elegida = cuentas[indice]
            return _menu(elegida, True)

    if estado.paso == PERIODO and estado.pedido:
        periodo = interpretar(texto, hoy)
        if periodo is None:
            indice = _opcion_elegida(t, [f"Cosecha {cosecha_de(hoy)}", "Últimos 3 meses"])
            if indice is None:
                return _pedir_periodo(estado, hoy, "No entendí el período.")
            periodo = interpretar("ultima cosecha" if indice == 0 else "ultimos 3 meses", hoy)
        return Respuesta(
            texto="Preparando…",
            estado=Estado(MENU, elegida.clientecuit),
            accion=estado.pedido,
            periodo=periodo,
            cuenta=elegida,
        )

    opciones = ["Ver estadísticas", "Descargar reporte", "Mis contactos"]
    if len(cuentas) > 1:
        opciones.append("Cambiar de cuenta")
    indice = _opcion_elegida(t, opciones)

    if indice == 0 or "estadistica" in t:
        return _pedir_periodo(Estado(PERIODO, elegida.clientecuit, ESTADISTICAS), hoy)
    if indice == 1 or "reporte" in t or "pdf" in t:
        return _pedir_periodo(Estado(PERIODO, elegida.clientecuit, REPORTE), hoy)
    if indice == 2 or "contacto" in t:
        return Respuesta(
            texto=("Mis contactos" if puede_administrar else
                   "Sólo quien administra los contactos puede agregarlos o quitarlos."),
            estado=Estado(MENU, elegida.clientecuit),
            accion=CONTACTOS if puede_administrar else None,
        )
    if indice == 3:
        return _pedir_cuenta(cuentas)
    return _menu(elegida, len(cuentas) > 1)


def _opcion_elegida(texto: str, opciones: list[str]) -> int | None:
    """Acepta el número del botón o el texto de la opción."""
    if texto.isdigit():
        indice = int(texto) - 1
        return indice if 0 <= indice < len(opciones) else None
    for i, opcion in enumerate(opciones):
        if _normalizar(opcion) == texto:
            return i
    return None
