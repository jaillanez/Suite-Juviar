"""Diálogo del bot. Función pura: no sabe de WhatsApp ni de bases.

Reproduce el recorrido que el productor ya conoce —cuenta, estadísticas o
reporte, período— y agrega la gestión de contactos y la oferta de uva de la temporada.
Guarda dónde quedó cada teléfono para que "Últimos 3 meses" se entienda después
de "Ver estadísticas".

Las ofertas y los turnos se leen y se guardan a través de ``Turnos`` (inyectado): el
diálogo no sabe de SQL. El bot no da días: la bodega los asigna desde Gestión.

Un número que la bodega no dio de alta puede consultar como en el bot anterior: escribe el
Número de CUENTA, el CUIT o la Patente del camión y queda vinculado a esa cuenta hasta que
escribe «Salir» (infra/044). Con ese vínculo ve estadísticas, el informe y los comprobantes;
ofrecer uva, turnos y contactos siguen siendo sólo para los números dados de alta. La búsqueda
pasa por ``Identificador`` (inyectado), que es quien cuenta los intentos.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Protocol

from .periodos import Periodo, cosecha_de, interpretar
from .turnos import (
    KG_MAX_OFERTA,
    KG_MIN_OFERTA,
    NOMBRE_SEDE,
    SEDES,
    VARIEDADES_MOSTRADAS,
    Borrador,
    OfertaRechazada,
    Turnos,
    dia_corto,
    dia_largo,
    kilos_escritos,
    miles,
    motivo_en_palabras,
)

MENU, PERIODO, CUENTA = "menu", "periodo", "cuenta"
ESTADISTICAS, REPORTE, CONTACTOS = "estadisticas", "reporte", "contactos"
OFRECER_UVA, MIS_TURNOS, CAMBIAR_CUENTA = "ofrecer_uva", "mis_turnos", "cambiar_cuenta"
OFERTA_CUENTA, OFERTA_SEDE, OFERTA_VARIEDAD = "oferta_cuenta", "oferta_sede", "oferta_variedad"
OFERTA_KG, OFERTA_ORGANICA, OFERTA_CONFIRMAR = "oferta_kg", "oferta_organica", "oferta_confirmar"
TAREA_TURNOS = "pedir_turnos"
COMPROBANTE, SALIR = "comprobante", "salir"
IDENTIFICAR, ELEGIR_VINCULO = "identificar", "elegir_vinculo"
VINCULAR, DESVINCULAR = "vincular", "desvincular"

NO_REGISTRADO = (
    "Este número no está registrado para consultar entregas.\n"
    "Pedile a la bodega que lo dé de alta, o a alguien que ya esté registrado "
    "que te invite.\n"
    "Para postularte a un trabajo, mandá tu CV en PDF o una foto."
)
SIN_PERMISO_INFORMES = (
    "Este número puede ofrecer uva y ver sus turnos, pero no ver entregas.\n"
    "Si necesitás los informes, pedíselo a quien administra los contactos."
)
CADUCADO = "Pasó un rato desde tu última consulta. Empecemos de nuevo."
PEDIR_DATO = (
    "Para consultar tus descargas, escribí tu *Número de CUENTA*, *CUIT* o *Patente de camión*.\n"
    "Para postularte a un trabajo, mandá tu CV en PDF o una foto."
)
DESVINCULADA = (
    "Tu cuenta fue desvinculada. La próxima vez que escribas te vamos a pedir de nuevo "
    "el número de cuenta."
)
DEMASIADOS_INTENTOS = (
    "Hubo demasiados intentos sin encontrar la cuenta. Probá de nuevo en una hora, "
    "o pedile a la bodega que dé de alta este número."
)
CUIT_INVALIDO = "Ese CUIT no es válido: revisá los 11 números."
_DESCRIPCION_DATO = {"cuenta": "la cuenta", "cuit": "el CUIT", "patente": "la patente"}
MINUTOS_SESION = 30

_ETIQUETAS = {
    ESTADISTICAS: "Ver estadísticas",
    REPORTE: "Descargar reporte",
    COMPROBANTE: "Comprobante de descarga",
    OFRECER_UVA: "Ofrecer uva",
    MIS_TURNOS: "Mis turnos",
    CONTACTOS: "Mis contactos",
    CAMBIAR_CUENTA: "Cambiar de cuenta",
    SALIR: "Salir",
}
_SALUDOS = {"volver", "menu", "menú", "0", "hola", "buenas", "buen dia", "buenas tardes"}
ULTIMA_DESCARGA = "Última descarga"
_SI = {"si", "s", "dale", "ok", "confirmar", "confirmo"}
_NO = {"no", "n", "cancelar", "cancelo"}


@dataclass(frozen=True)
class Cuenta:
    clientecuit: str
    codigo: str
    titular: str
    tareas: frozenset[str] = frozenset()

    def como_opcion(self) -> str:
        return f"{self.titular.strip().rstrip('.')} ({self.codigo})"

    def como_opcion_vinculo(self) -> str:
        """Como en el bot anterior: «G03436 — ENAV S.A.»."""
        return f"{self.codigo} — {self.titular.strip().rstrip('.')}"


class IdentificacionBloqueada(Exception):
    """El teléfono pasó el tope de intentos sin resultado de la última hora."""


class Identificador(Protocol):
    def buscar(self, por: str, dato: str) -> list[Cuenta]: ...


@dataclass(frozen=True)
class Estado:
    paso: str = MENU
    cuenta: str | None = None      # clientecuit elegido
    pedido: str | None = None      # estadisticas | reporte
    turno: Borrador | None = None  # oferta de uva en curso
    candidatas: tuple[str, ...] = ()  # clientecuit entre los que elige quien no está dado de alta


@dataclass
class Respuesta:
    texto: str
    opciones: list[str] = field(default_factory=list)
    estado: Estado = field(default_factory=Estado)
    accion: str | None = None              # estadisticas | reporte | contactos
    periodo: Periodo | None = None
    cuenta: Cuenta | None = None
    ciu: str | None = None                 # comprobante pedido (None: el de la última descarga)
    desde: int = 0                         # «Ver más…» de una lista de Meta: desde qué opción

    def con_botones(self) -> str:
        if not self.opciones:
            return self.texto
        lineas = "\n".join(f"{i} — {o}" for i, o in enumerate(self.opciones, start=1))
        return f"{self.texto}\n\n{lineas}"


@dataclass(frozen=True)
class _Contexto:
    cuentas: list[Cuenta]
    cuentas_turno: list[Cuenta]
    informes: bool
    administrar: bool
    turnos: Turnos | None
    hoy_turnos: date
    abierta: bool = False  # vínculo por cuenta, CUIT o patente (sin alta de la bodega)

    def menu(self) -> list[str]:
        if self.abierta:
            return [ESTADISTICAS, REPORTE, COMPROBANTE, CAMBIAR_CUENTA, SALIR]
        claves = [ESTADISTICAS, REPORTE, COMPROBANTE] if self.informes else []
        if self.cuentas_turno:
            claves += [OFRECER_UVA, MIS_TURNOS]
        claves.append(CONTACTOS)
        if len(self.cuentas) > 1:
            claves.append(CAMBIAR_CUENTA)
        return claves


def _sin_prefijo(texto: str | None) -> str | None:
    """Los botones de Meta vuelven con su id (``op:<opción>``): se toma la opción completa,
    que no depende del título recortado del botón."""
    if texto and texto.startswith("op:"):
        return texto[3:]
    return texto


def _pagina(texto: str | None) -> int | None:
    coincide = re.fullmatch(r"pag:(\d{1,3})", texto or "")
    return int(coincide.group(1)) if coincide else None


def _normalizar(texto: str | None) -> str:
    limpio = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    return "".join(c for c in limpio if not unicodedata.combining(c))


def _nombre(cuenta: Cuenta) -> str:
    return cuenta.titular.strip().rstrip(".")


def _menu(cuenta: Cuenta, ctx: _Contexto, aviso: str = "") -> Respuesta:
    encabezado = f"{_nombre(cuenta)} — Cuenta {cuenta.codigo}\n¿Qué querés consultar?"
    return Respuesta(
        texto=f"{aviso}\n\n{encabezado}" if aviso else encabezado,
        opciones=[_ETIQUETAS[c] for c in ctx.menu()],
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
    puede_pedir_turnos: bool = False,
    turnos: Turnos | None = None,
    hoy_turnos: date | None = None,
    sesion_abierta: bool = False,
    identificar: Identificador | None = None,
    candidatas: list[Cuenta] | None = None,
) -> Respuesta:
    """``hoy`` es la fecha de las estadísticas (puede estar simulada);
    ``hoy_turnos`` es la fecha real de San Juan, la única que vale para ofertas y turnos.

    ``sesion_abierta``: ``cuentas`` es la única cuenta vinculada por cuenta, CUIT o patente.
    ``identificar``: un número sin cuentas puede vincularse; sin él, sigue «no registrado».
    ``candidatas``: las cuentas de ``estado.candidatas``, ya leídas."""
    pagina = _pagina(texto)
    if pagina is not None:
        # «Ver más…» de una lista: se repite la misma pregunta desde esa opción.
        respuesta = responder(
            None, cuentas, estado, hoy, puede_ver_informes, puede_administrar, puede_pedir_turnos,
            turnos, hoy_turnos, sesion_abierta, identificar, candidatas,
        )
        respuesta.desde = pagina if pagina < len(respuesta.opciones) else 0
        return respuesta
    texto = _sin_prefijo(texto)
    if not cuentas:
        if identificar is None:
            return Respuesta(NO_REGISTRADO)
        return _identificacion(texto, estado, identificar, candidatas or [], hoy)
    if sesion_abierta:
        # El vínculo abierto sólo consulta: nunca ofrece uva, ve turnos ni administra contactos.
        cuentas = cuentas[:1]
        puede_ver_informes, puede_administrar, puede_pedir_turnos = True, False, False
    cuentas_turno = (
        [c for c in cuentas if TAREA_TURNOS in c.tareas]
        if puede_pedir_turnos and turnos is not None
        else []
    )
    if not puede_ver_informes:
        if not cuentas_turno:
            return Respuesta(SIN_PERMISO_INFORMES)
        cuentas = cuentas_turno
    ctx = _Contexto(
        cuentas, cuentas_turno, puede_ver_informes, puede_administrar, turnos,
        hoy_turnos or hoy, sesion_abierta,
    )

    t = _normalizar(texto)
    elegida = next((c for c in cuentas if c.clientecuit == estado.cuenta), None)

    # Volver o empezar de nuevo, desde cualquier paso.
    if t in _SALUDOS:
        if elegida or len(cuentas) == 1:
            return _menu(elegida or cuentas[0], ctx)
        return _pedir_cuenta(cuentas)
    if ctx.abierta and t in {"salir", "desvincular", "cerrar sesion"}:
        return Respuesta(DESVINCULADA, estado=Estado(IDENTIFICAR), accion=DESVINCULAR)

    if estado.paso == OFERTA_CUENTA and cuentas_turno:
        indice = _opcion_elegida(t, [c.como_opcion() for c in cuentas_turno])
        if indice is None:
            return _pedir_cuenta_oferta(cuentas_turno)
        return _pedir_sede(cuentas_turno[indice])

    if estado.paso == CUENTA or elegida is None:
        if len(cuentas) == 1:
            elegida = cuentas[0]
        else:
            indice = _opcion_elegida(t, [c.como_opcion() for c in cuentas])
            if indice is None:
                return _pedir_cuenta(cuentas)
            elegida = cuentas[indice]
            return _menu(elegida, ctx)

    # Una sesión del pedido de turno por día (anterior a las ofertas) vuelve al menú.
    if estado.paso.startswith("turno_"):
        return _menu(elegida, ctx)
    if estado.paso.startswith("oferta_"):
        if elegida not in cuentas_turno or ctx.turnos is None:
            return _menu(elegida, ctx)
        if t in {"cancelar", "salir"}:
            return _menu(elegida, ctx, "Listo, no envié ninguna oferta.")
        if estado.turno is None:
            return _pedir_sede(elegida)
        return _paso_oferta(texto, t, elegida, estado.paso, estado.turno, ctx)

    if estado.paso == PERIODO and estado.pedido and ctx.informes:
        periodo = interpretar(texto, hoy)
        if periodo is None:
            indice = _opcion_elegida(t, [f"Cosecha {cosecha_de(hoy)}", "Últimos 3 meses"])
            if indice is None:
                return _pedir_periodo(estado, hoy, "No entendí el período." if t else "")
            periodo = interpretar("ultima cosecha" if indice == 0 else "ultimos 3 meses", hoy)
        return Respuesta(
            texto="Preparando…",
            estado=Estado(MENU, elegida.clientecuit),
            accion=estado.pedido,
            periodo=periodo,
            cuenta=elegida,
        )

    if estado.paso == COMPROBANTE and ctx.informes:
        return _paso_comprobante(texto, t, elegida, ctx)

    claves = ctx.menu()
    indice = _opcion_elegida(t, [_ETIQUETAS[c] for c in claves])
    clave = claves[indice] if indice is not None else _clave_por_palabras(t)

    if clave is None and ctx.informes and (ciu := _ciu_escrito(texto)):
        return _pedir_comprobante(elegida, ciu)
    if clave in {ESTADISTICAS, REPORTE, COMPROBANTE} and not ctx.informes:
        return _menu(elegida, ctx, SIN_PERMISO_INFORMES)
    if clave == COMPROBANTE:
        return _preguntar_comprobante(elegida)
    if ctx.abierta and clave == SALIR:
        return Respuesta(DESVINCULADA, estado=Estado(IDENTIFICAR), accion=DESVINCULAR)
    if ctx.abierta and clave == CAMBIAR_CUENTA:
        return Respuesta(
            f"Listo, desvinculé la cuenta {elegida.codigo}.\n{PEDIR_DATO}",
            estado=Estado(IDENTIFICAR), accion=DESVINCULAR,
        )
    if clave == ESTADISTICAS:
        return _pedir_periodo(Estado(PERIODO, elegida.clientecuit, ESTADISTICAS), hoy)
    if clave == REPORTE:
        return _pedir_periodo(Estado(PERIODO, elegida.clientecuit, REPORTE), hoy)
    if clave == OFRECER_UVA and cuentas_turno:
        return _iniciar_oferta(elegida, ctx)
    if clave == MIS_TURNOS and cuentas_turno:
        return _mis_turnos(elegida, ctx)
    if clave == CONTACTOS and not ctx.abierta:
        return Respuesta(
            texto=("Mis contactos" if puede_administrar else
                   "Sólo quien administra los contactos puede agregarlos o quitarlos."),
            estado=Estado(MENU, elegida.clientecuit),
            accion=CONTACTOS if puede_administrar else None,
        )
    if clave == CAMBIAR_CUENTA and len(cuentas) > 1:
        return _pedir_cuenta(cuentas)
    return _menu(elegida, ctx)


def _clave_por_palabras(t: str) -> str | None:
    if "estadistica" in t:
        return ESTADISTICAS
    if "comprobante" in t or "ddjj" in t:
        return COMPROBANTE
    if "reporte" in t or "pdf" in t or "informe" in t:
        return REPORTE
    if "turno" in t:
        return MIS_TURNOS
    if "ofrecer" in t or "oferta" in t:
        return OFRECER_UVA
    if "contacto" in t:
        return CONTACTOS
    return None


def _opcion_elegida(texto: str, opciones: list[str]) -> int | None:
    """Acepta el número del botón o el texto de la opción."""
    if texto.isdigit():
        indice = int(texto) - 1
        return indice if 0 <= indice < len(opciones) else None
    for i, opcion in enumerate(opciones):
        if _normalizar(opcion) == texto:
            return i
    return None


# --- Comprobante DDJJ --------------------------------------------------------------


def _ciu_escrito(texto: str | None) -> str | None:
    """Número de CIU escrito a mano: «17377», «CIU 0000017377», «N° 17377». Un CUIT (11
    números) no es un CIU; tampoco los números cortos del menú."""
    limpio = _normalizar(texto)
    for _ in range(2):
        limpio = re.sub(r"^(ciu|comprobante|ddjj|nro|numero|n[°º.o]?|#)[\s:.°º]*", "", limpio)
    return limpio if re.fullmatch(r"\d{4,10}", limpio) else None


def _preguntar_comprobante(cuenta: Cuenta, aviso: str = "") -> Respuesta:
    return Respuesta(
        texto=_con_aviso(aviso, "Escribí el número de CIU del comprobante que necesitás, "
                                f"o elegí «{ULTIMA_DESCARGA}»."),
        opciones=[ULTIMA_DESCARGA, "Volver"],
        estado=Estado(COMPROBANTE, cuenta.clientecuit),
    )


def _pedir_comprobante(cuenta: Cuenta, ciu: str | None) -> Respuesta:
    return Respuesta(
        texto="Preparando…",
        estado=Estado(MENU, cuenta.clientecuit),
        accion=COMPROBANTE,
        cuenta=cuenta,
        ciu=ciu,
    )


def _paso_comprobante(texto: str | None, t: str, cuenta: Cuenta, ctx: _Contexto) -> Respuesta:
    indice = _opcion_elegida(t, [ULTIMA_DESCARGA, "Volver"])
    if indice == 0 or t in {"ultima", "la ultima", "ultimo"}:
        return _pedir_comprobante(cuenta, None)
    if indice == 1:
        return _menu(cuenta, ctx)
    ciu = _ciu_escrito(texto)
    if ciu:
        return _pedir_comprobante(cuenta, ciu)
    return _preguntar_comprobante(cuenta, "No entendí el número de CIU." if t else "")


# --- Acceso sin alta: cuenta, CUIT o patente ------------------------------------------


def cuit_valido(cuit: str) -> bool:
    if not re.fullmatch(r"\d{11}", cuit):
        return False
    suma = sum(int(d) * p for d, p in zip(cuit[:10], (5, 4, 3, 2, 7, 6, 5, 4, 3, 2), strict=True))
    verificador = 11 - suma % 11
    verificador = {11: 0, 10: 9}.get(verificador, verificador)
    return verificador == int(cuit[10])


def dato_de_cuenta(texto: str | None) -> tuple[str, str] | None:
    """(«cuenta» | «cuit» | «patente», dato normalizado) o None si no parece ninguno."""
    limpio = re.sub(r"[\s.\-/]", "", (texto or "").upper())
    limpio = re.sub(r"^(CUIT|CUENTA|PATENTE|DOMINIO)[:Nº°]*", "", limpio)
    if re.fullmatch(r"[A-Z]\d{5}", limpio):
        return "cuenta", limpio
    if re.fullmatch(r"\d{11}", limpio):
        return "cuit", limpio
    if (re.fullmatch(r"[A-Z0-9]{5,10}", limpio) and re.search(r"[A-Z]", limpio)
            and re.search(r"\d", limpio)):
        return "patente", limpio
    return None


def _pedir_vinculo(candidatas: list[Cuenta], texto: str) -> Respuesta:
    return Respuesta(
        texto=texto,
        opciones=[c.como_opcion_vinculo() for c in candidatas],
        estado=Estado(ELEGIR_VINCULO, candidatas=tuple(c.clientecuit for c in candidatas)),
    )


def _vincular(cuenta: Cuenta, hoy: date) -> Respuesta:
    ctx = _Contexto([cuenta], [], True, False, None, hoy, abierta=True)
    respuesta = _menu(cuenta, ctx, f"Listo, este número quedó vinculado a la cuenta {cuenta.codigo} "
                                   "hasta que escribas «Salir».")
    respuesta.accion = VINCULAR
    respuesta.cuenta = cuenta
    return respuesta


def _identificacion(
    texto: str | None, estado: Estado, identificar: Identificador, candidatas: list[Cuenta],
    hoy: date,
) -> Respuesta:
    t = _normalizar(texto)
    if estado.paso == ELEGIR_VINCULO and candidatas:
        indice = _opcion_elegida(t, [c.como_opcion_vinculo() for c in candidatas])
        if indice is not None:
            return _vincular(candidatas[indice], hoy)
        if dato_de_cuenta(texto) is None:
            return _pedir_vinculo(
                candidatas, _con_aviso("No entendí cuál." if t else "", "¿Con qué cuenta querés operar?"))
    dato = dato_de_cuenta(texto)
    if dato is None:
        aviso = "No reconocí ese dato." if t and t not in _SALUDOS and estado.paso == IDENTIFICAR else ""
        return Respuesta(_con_aviso(aviso, PEDIR_DATO), estado=Estado(IDENTIFICAR))
    por, valor = dato
    if por == "cuit" and not cuit_valido(valor):
        return Respuesta(f"{CUIT_INVALIDO}\n{PEDIR_DATO}", estado=Estado(IDENTIFICAR))
    try:
        encontradas = identificar.buscar(por, valor)
    except IdentificacionBloqueada:
        return Respuesta(DEMASIADOS_INTENTOS, estado=Estado(IDENTIFICAR))
    if not encontradas:
        return Respuesta(
            f"No encontré ninguna cuenta con {_DESCRIPCION_DATO[por]} *{valor}*.\n{PEDIR_DATO}",
            estado=Estado(IDENTIFICAR),
        )
    if len(encontradas) == 1:
        return _vincular(encontradas[0], hoy)
    quien = _DESCRIPCION_DATO[por]
    asociado = {"patente": "entregó para", "cuit": "está asociado a"}.get(por, "corresponde a")
    return _pedir_vinculo(
        encontradas,
        f"{quien[0].upper()}{quien[1:]} *{valor}* {asociado} *{len(encontradas)} cuentas*.\n"
        "¿Con cuál querés operar?",
    )


# --- Ofrecer uva ------------------------------------------------------------------


def _con_aviso(aviso: str, texto: str) -> str:
    return f"{aviso}\n{texto}" if aviso else texto


def _estado_oferta(cuenta: Cuenta, paso: str, borrador: Borrador) -> Estado:
    return Estado(paso, cuenta.clientecuit, None, borrador)


def _iniciar_oferta(elegida: Cuenta, ctx: _Contexto) -> Respuesta:
    # La cuenta del menú ya la eligió; sólo se pregunta si esa no puede ofrecer.
    if elegida in ctx.cuentas_turno:
        return _pedir_sede(elegida)
    if len(ctx.cuentas_turno) == 1:
        return _pedir_sede(ctx.cuentas_turno[0])
    return _pedir_cuenta_oferta(ctx.cuentas_turno)


def _pedir_cuenta_oferta(cuentas_turno: list[Cuenta]) -> Respuesta:
    if not cuentas_turno:
        return Respuesta(texto="Este número no tiene permiso para ofrecer uva.")
    return Respuesta(
        texto="¿Para qué cuenta es la oferta?",
        opciones=[c.como_opcion() for c in cuentas_turno],
        estado=Estado(OFERTA_CUENTA, cuentas_turno[0].clientecuit),
    )


def _pedir_sede(cuenta: Cuenta, aviso: str = "") -> Respuesta:
    texto = (f"Oferta de uva de {_nombre(cuenta)} ({cuenta.codigo}) para toda la temporada.\n"
             "¿En qué bodega vas a entregar?")
    return Respuesta(
        texto=_con_aviso(aviso, texto),
        opciones=[nombre for _, nombre in SEDES],
        estado=_estado_oferta(cuenta, OFERTA_SEDE, Borrador()),
    )


def _lineas(borrador: Borrador) -> str:
    return "\n".join(f"• {v}: {miles(kg)} kg" for v, kg in borrador.lineas)


def _pedir_variedad(cuenta: Cuenta, borrador: Borrador, ctx: _Contexto, aviso: str = "") -> Respuesta:
    assert ctx.turnos is not None
    ya = {_normalizar(v) for v, _ in borrador.lineas}
    opciones = [v for v in ctx.turnos.variedades(cuenta.clientecuit)
                if _normalizar(v) not in ya][:VARIEDADES_MOSTRADAS]
    if borrador.lineas:
        texto = (f"Anotado hasta ahora:\n{_lineas(borrador)}\n"
                 "¿Ofrecés otra variedad? Si no, elegí «Listo, no hay más».")
        extra = ["Listo, no hay más"]
    else:
        texto = "¿Qué variedad ofrecés? Después te pregunto por las otras."
        extra = []
    texto += "\nSi no está en la lista, escribí el nombre."
    return Respuesta(
        texto=_con_aviso(aviso, texto),
        opciones=opciones + extra,
        estado=_estado_oferta(cuenta, OFERTA_VARIEDAD,
                              replace(borrador, variedad=None, opciones=tuple(opciones))),
    )


def _pedir_kg(cuenta: Cuenta, borrador: Borrador, aviso: str = "") -> Respuesta:
    texto = (f"¿Cuántos kilos de {borrador.variedad} ofrecés para toda la temporada?\n"
             'Escribilo en kilos o en toneladas, por ejemplo "80.000" o "80 t".')
    return Respuesta(texto=_con_aviso(aviso, texto), estado=_estado_oferta(cuenta, OFERTA_KG, borrador))


def _pedir_organica(cuenta: Cuenta, borrador: Borrador, aviso: str = "") -> Respuesta:
    return Respuesta(
        texto=_con_aviso(aviso, "¿Esta uva es orgánica?"),
        opciones=["Sí, orgánica", "No"],
        estado=_estado_oferta(cuenta, OFERTA_ORGANICA, borrador),
    )


def _resumen(cuenta: Cuenta, borrador: Borrador, aviso: str = "") -> Respuesta:
    assert borrador.sede and borrador.lineas
    texto = (
        "Revisá tu oferta:\n"
        f"Cuenta: {_nombre(cuenta)} ({cuenta.codigo})\n"
        f"Bodega: {NOMBRE_SEDE[borrador.sede]}\n"
        f"{_lineas(borrador)}\n"
        f"Total: {miles(borrador.total)} kg\n"
        + (f"Uva orgánica: {'sí' if borrador.organica else 'no'}\n" if borrador.organica is not None else "")
        + "La bodega la revisa y te avisa por acá qué días te toca entregar.\n¿La envío?"
    )
    return Respuesta(
        texto=_con_aviso(aviso, texto),
        opciones=["Sí, enviar la oferta", "No, cancelar"],
        estado=_estado_oferta(cuenta, OFERTA_CONFIRMAR, borrador),
    )


def _terminar_variedades(cuenta: Cuenta, borrador: Borrador, ctx: _Contexto) -> Respuesta:
    assert ctx.turnos is not None
    if ctx.turnos.tiene_organico(cuenta.clientecuit, ctx.hoy_turnos):
        return _pedir_organica(cuenta, borrador)
    return _resumen(cuenta, replace(borrador, organica=None))


def _variedad_escrita(texto: str | None) -> str | None:
    limpio = " ".join((texto or "").split())
    if not 2 <= len(limpio) <= 60 or not any(c.isalpha() for c in limpio):
        return None
    return limpio[0].upper() + limpio[1:]


def _paso_oferta(
    texto: str | None, t: str, cuenta: Cuenta, paso: str, borrador: Borrador, ctx: _Contexto
) -> Respuesta:
    assert ctx.turnos is not None
    if paso == OFERTA_SEDE or borrador.sede is None:
        indice = _opcion_elegida(t, [nombre for _, nombre in SEDES])
        if indice is None:
            return _pedir_sede(cuenta, "No entendí la bodega.")
        return _pedir_variedad(cuenta, replace(borrador, sede=SEDES[indice][0]), ctx)

    if paso == OFERTA_VARIEDAD:
        opciones = list(borrador.opciones) + (["Listo, no hay más"] if borrador.lineas else [])
        indice = _opcion_elegida(t, opciones)
        if t in {"listo", "no", "ninguna"} or (borrador.lineas and indice == len(opciones) - 1):
            if not borrador.lineas:
                return _pedir_variedad(cuenta, borrador, ctx, "Todavía no anotaste ninguna variedad.")
            return _terminar_variedades(cuenta, borrador, ctx)
        variedad = opciones[indice] if indice is not None else _variedad_escrita(texto)
        if variedad is None:
            return _pedir_variedad(cuenta, borrador, ctx, "No entendí la variedad." if t else "")
        return _pedir_kg(cuenta, replace(borrador, variedad=variedad))

    if paso == OFERTA_KG and borrador.variedad:
        kilos = kilos_escritos(texto)
        if kilos is None or not KG_MIN_OFERTA <= kilos <= KG_MAX_OFERTA:
            return _pedir_kg(cuenta, borrador,
                             f"No me cerró ese valor: tiene que ser de {miles(KG_MIN_OFERTA)} kg en adelante.")
        otras = tuple(linea for linea in borrador.lineas
                      if _normalizar(linea[0]) != _normalizar(borrador.variedad))
        return _pedir_variedad(cuenta, replace(borrador, lineas=otras + ((borrador.variedad, kilos),)), ctx)

    if paso == OFERTA_ORGANICA:
        indice = _opcion_elegida(t, ["Sí, orgánica", "No"])
        if indice == 0 or t in _SI or t == "organica":
            return _resumen(cuenta, replace(borrador, organica=True))
        if indice == 1 or t in _NO or t.startswith("no "):
            return _resumen(cuenta, replace(borrador, organica=False))
        return _pedir_organica(cuenta, borrador, "Respondé 1 (sí) o 2 (no).")

    if paso == OFERTA_CONFIRMAR and borrador.lineas:
        indice = _opcion_elegida(t, ["Sí, enviar la oferta", "No, cancelar"])
        if indice == 1 or t in _NO:
            return _menu(cuenta, ctx, "Listo, no envié ninguna oferta.")
        if indice != 0 and t not in _SI:
            return _resumen(cuenta, borrador, "Respondé 1 para enviar la oferta o 2 para cancelar.")
        return _enviar(cuenta, borrador, ctx)

    return _menu(cuenta, ctx)


def _enviar(cuenta: Cuenta, borrador: Borrador, ctx: _Contexto) -> Respuesta:
    assert ctx.turnos is not None and borrador.sede
    try:
        # El mismo pedido y variedad no se duplican: si se reintenta, la base devuelve la misma.
        for variedad, kg in borrador.lineas:
            ctx.turnos.ofrecer(borrador.pedido, cuenta.clientecuit, cuenta.codigo, borrador.sede,
                               variedad, kg, bool(borrador.organica))
    except OfertaRechazada as exc:
        return _menu(cuenta, ctx, f"No pude enviar la oferta: {motivo_en_palabras(str(exc))}")
    aviso = (
        f"¡Listo! Tu oferta de {miles(borrador.total)} kg para {NOMBRE_SEDE[borrador.sede]} quedó enviada.\n"
        'La bodega te va a avisar por acá los días. Mientras tanto la ves en "Mis turnos".'
    )
    return _menu(cuenta, ctx, aviso)


_ESTADO_OFERTA = {
    "pendiente": "esperando que la bodega asigne los días",
    "asignada": "con días asignados",
}


def _mis_turnos(elegida: Cuenta, ctx: _Contexto) -> Respuesta:
    assert ctx.turnos is not None
    hoy = ctx.hoy_turnos
    cuits = [c.clientecuit for c in ctx.cuentas_turno]
    varias = len(ctx.cuentas_turno) > 1
    ofertas = ctx.turnos.ofertas(cuits)
    proximos = ctx.turnos.proximos(cuits, hoy)
    if not ofertas and not proximos:
        return _menu(elegida, ctx, "No tenés ofertas ni turnos de hoy en adelante.")
    partes = []
    if ofertas:
        lineas = []
        for o in ofertas:
            if o.estado == "detenida":
                estado = ("postergada por falta de grado"
                          + (f" hasta el {dia_largo(o.detenida_hasta)}" if o.detenida_hasta else ""))
            else:
                estado = _ESTADO_OFERTA.get(o.estado, o.estado)
            linea = f"• {o.variedad}, {miles(o.kg)} kg en {NOMBRE_SEDE.get(o.sede, o.sede)}: {estado}"
            if varias and o.codigo:
                linea += f" — {o.codigo}"
            lineas.append(linea)
        partes.append("Tus ofertas:\n" + "\n".join(lineas))
    if proximos:
        lineas = []
        for turno in proximos:
            camiones = "camión" if turno.camiones == 1 else "camiones"
            linea = (
                f"• {dia_corto(turno.fecha, hoy)} — {NOMBRE_SEDE.get(turno.sede, turno.sede)} — "
                f"{turno.camiones} {camiones} de {miles(turno.kg_por_camion)} kg"
            )
            if turno.organica:
                linea += ", orgánica"
            if turno.camiones_usados:
                linea += f" (ya llegaron {turno.camiones_usados})"
            if varias and turno.codigo:
                linea += f" — {turno.codigo}"
            lineas.append(linea)
        partes.append("Tus próximos días:\n" + "\n".join(lineas))
    return _menu(elegida, ctx, "\n\n".join(partes))
