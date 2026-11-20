"""Diálogo del bot. Función pura: no sabe de WhatsApp ni de bases.

Reproduce el recorrido que el productor ya conoce —cuenta, estadísticas o
reporte, período— y agrega la gestión de contactos y la oferta de uva de la temporada.
Guarda dónde quedó cada teléfono para que "Últimos 3 meses" se entienda después
de "Ver estadísticas".

Las ofertas y los turnos se leen y se guardan a través de ``Turnos`` (inyectado): el
diálogo no sabe de SQL. El bot no da días: la bodega los asigna desde Gestión.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date

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
MINUTOS_SESION = 30

_ETIQUETAS = {
    ESTADISTICAS: "Ver estadísticas",
    REPORTE: "Descargar reporte",
    OFRECER_UVA: "Ofrecer uva",
    MIS_TURNOS: "Mis turnos",
    CONTACTOS: "Mis contactos",
    CAMBIAR_CUENTA: "Cambiar de cuenta",
}
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


@dataclass(frozen=True)
class Estado:
    paso: str = MENU
    cuenta: str | None = None      # clientecuit elegido
    pedido: str | None = None      # estadisticas | reporte
    turno: Borrador | None = None  # oferta de uva en curso


@dataclass
class Respuesta:
    texto: str
    opciones: list[str] = field(default_factory=list)
    estado: Estado = field(default_factory=Estado)
    accion: str | None = None              # estadisticas | reporte | contactos
    periodo: Periodo | None = None
    cuenta: Cuenta | None = None

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

    def menu(self) -> list[str]:
        claves = [ESTADISTICAS, REPORTE] if self.informes else []
        if self.cuentas_turno:
            claves += [OFRECER_UVA, MIS_TURNOS]
        claves.append(CONTACTOS)
        if len(self.cuentas) > 1:
            claves.append(CAMBIAR_CUENTA)
        return claves


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
) -> Respuesta:
    """``hoy`` es la fecha de las estadísticas (puede estar simulada);
    ``hoy_turnos`` es la fecha real de San Juan, la única que vale para ofertas y turnos."""
    if not cuentas:
        return Respuesta(NO_REGISTRADO)
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
        hoy_turnos or hoy,
    )

    t = _normalizar(texto)
    elegida = next((c for c in cuentas if c.clientecuit == estado.cuenta), None)

    # Volver o empezar de nuevo, desde cualquier paso.
    if t in {"volver", "menu", "menú", "0", "hola", "buenas", "buen dia", "buenas tardes"}:
        if elegida or len(cuentas) == 1:
            return _menu(elegida or cuentas[0], ctx)
        return _pedir_cuenta(cuentas)

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
                return _pedir_periodo(estado, hoy, "No entendí el período.")
            periodo = interpretar("ultima cosecha" if indice == 0 else "ultimos 3 meses", hoy)
        return Respuesta(
            texto="Preparando…",
            estado=Estado(MENU, elegida.clientecuit),
            accion=estado.pedido,
            periodo=periodo,
            cuenta=elegida,
        )

    claves = ctx.menu()
    indice = _opcion_elegida(t, [_ETIQUETAS[c] for c in claves])
    clave = claves[indice] if indice is not None else _clave_por_palabras(t)

    if clave in {ESTADISTICAS, REPORTE} and not ctx.informes:
        return _menu(elegida, ctx, SIN_PERMISO_INFORMES)
    if clave == ESTADISTICAS:
        return _pedir_periodo(Estado(PERIODO, elegida.clientecuit, ESTADISTICAS), hoy)
    if clave == REPORTE:
        return _pedir_periodo(Estado(PERIODO, elegida.clientecuit, REPORTE), hoy)
    if clave == OFRECER_UVA and cuentas_turno:
        return _iniciar_oferta(elegida, ctx)
    if clave == MIS_TURNOS and cuentas_turno:
        return _mis_turnos(elegida, ctx)
    if clave == CONTACTOS:
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
    if "reporte" in t or "pdf" in t:
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
            return _pedir_variedad(cuenta, borrador, ctx, "No entendí la variedad.")
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
