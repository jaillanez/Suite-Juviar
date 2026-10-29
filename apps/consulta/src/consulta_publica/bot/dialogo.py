"""Diálogo del bot. Función pura: no sabe de WhatsApp ni de bases.

Reproduce el recorrido que el productor ya conoce —cuenta, estadísticas o
reporte, período— y agrega la gestión de contactos y el pedido de turnos.
Guarda dónde quedó cada teléfono para que "Últimos 3 meses" se entienda después
de "Ver estadísticas".

Los turnos se leen y se reservan a través de ``Turnos`` (inyectado): el diálogo no
sabe de SQL, y las reglas del cupo las aplica la base.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from .periodos import Periodo, cosecha_de, interpretar
from .turnos import (
    CAMIONES_MAX,
    DIAS_A_MIRAR,
    DIAS_MAXIMOS,
    DIAS_OFRECIDOS,
    KG_MAX_CAMION,
    KG_MIN_CAMION,
    KG_POR_DEFECTO,
    NOMBRE_SEDE,
    SEDES,
    Borrador,
    TurnoRechazado,
    Turnos,
    dia_corto,
    dia_largo,
    entero_escrito,
    fecha_escrita,
    kilos_escritos,
    miles,
    motivo_en_palabras,
    toneladas,
)

MENU, PERIODO, CUENTA = "menu", "periodo", "cuenta"
ESTADISTICAS, REPORTE, CONTACTOS = "estadisticas", "reporte", "contactos"
PEDIR_TURNO, MIS_TURNOS, CAMBIAR_CUENTA = "pedir_turno", "mis_turnos", "cambiar_cuenta"
TURNO_CUENTA, TURNO_SEDE, TURNO_DIA = "turno_cuenta", "turno_sede", "turno_dia"
TURNO_CAMIONES, TURNO_KG = "turno_camiones", "turno_kg"
TURNO_ORGANICA, TURNO_CONFIRMAR = "turno_organica", "turno_confirmar"
TAREA_TURNOS = "pedir_turnos"

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

_ETIQUETAS = {
    ESTADISTICAS: "Ver estadísticas",
    REPORTE: "Descargar reporte",
    PEDIR_TURNO: "Pedir turno",
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
    turno: Borrador | None = None  # pedido de turno en curso


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
            claves += [PEDIR_TURNO, MIS_TURNOS]
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
    ``hoy_turnos`` es la fecha real de San Juan, la única que vale para turnos."""
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

    if estado.paso == TURNO_CUENTA and cuentas_turno:
        indice = _opcion_elegida(t, [c.como_opcion() for c in cuentas_turno])
        if indice is None:
            return _pedir_cuenta_turno(cuentas_turno)
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

    if estado.paso.startswith("turno_"):
        if elegida not in cuentas_turno or ctx.turnos is None:
            return _menu(elegida, ctx)
        if t in {"cancelar", "salir"}:
            return _menu(elegida, ctx, "Listo, no pedí ningún turno.")
        return _paso_turno(texto, t, elegida, estado.paso, estado.turno or Borrador(), ctx)

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
    if clave == PEDIR_TURNO and cuentas_turno:
        return _iniciar_turno(elegida, ctx)
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
        return MIS_TURNOS if "mis" in t.split() else PEDIR_TURNO
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


# --- Pedir turno -----------------------------------------------------------------


def _estado_turno(cuenta: Cuenta, paso: str, borrador: Borrador) -> Estado:
    return Estado(paso, cuenta.clientecuit, None, borrador)


def _iniciar_turno(elegida: Cuenta, ctx: _Contexto) -> Respuesta:
    # La cuenta del menú ya la eligió; sólo se pregunta si esa no puede pedir turnos.
    if elegida in ctx.cuentas_turno:
        return _pedir_sede(elegida)
    if len(ctx.cuentas_turno) == 1:
        return _pedir_sede(ctx.cuentas_turno[0])
    return _pedir_cuenta_turno(ctx.cuentas_turno)


def _pedir_cuenta_turno(cuentas_turno: list[Cuenta]) -> Respuesta:
    if not cuentas_turno:
        return Respuesta(texto="Este número no tiene permiso para pedir turnos.")
    return Respuesta(
        texto="¿Para qué cuenta es el turno?",
        opciones=[c.como_opcion() for c in cuentas_turno],
        estado=Estado(TURNO_CUENTA, cuentas_turno[0].clientecuit),
    )


def _pedir_sede(cuenta: Cuenta, aviso: str = "") -> Respuesta:
    texto = f"Turno para {_nombre(cuenta)} ({cuenta.codigo}).\n¿En qué bodega vas a descargar?"
    return Respuesta(
        texto=f"{aviso}\n{texto}" if aviso else texto,
        opciones=[nombre for _, nombre in SEDES],
        estado=_estado_turno(cuenta, TURNO_SEDE, Borrador()),
    )


def _pedir_dia(cuenta: Cuenta, borrador: Borrador, ctx: _Contexto, aviso: str = "") -> Respuesta:
    assert ctx.turnos is not None and borrador.sede is not None
    hoy = ctx.hoy_turnos
    libres = ctx.turnos.libres(borrador.sede, hoy, hoy + timedelta(days=DIAS_A_MIRAR - 1))
    minimo = _kilos_necesarios(borrador)
    dias = [
        (dia, kg) for dia, kg in sorted(libres.items()) if hoy <= dia and kg >= minimo
    ][:DIAS_OFRECIDOS]
    sede = NOMBRE_SEDE[borrador.sede]
    if dias:
        texto = f"¿Qué día? Estos son los próximos días con lugar en {sede}."
    else:
        texto = f"En {sede} no quedan días con lugar en las próximas dos semanas."
    texto += '\nTambién podés escribir la fecha, por ejemplo "30/10".'
    return Respuesta(
        texto=f"{aviso}\n{texto}" if aviso else texto,
        opciones=[f"{dia_corto(dia, hoy)} — {toneladas(kg)} libres" for dia, kg in dias]
        + ["Otra bodega"],
        estado=_estado_turno(
            cuenta, TURNO_DIA, replace(borrador, fecha=None, dias=tuple(d for d, _ in dias))
        ),
    )


def _kilos_necesarios(borrador: Borrador) -> int:
    """Lo mínimo que tiene que quedar libre: un camión, o el pedido entero si ya lo dijo."""
    if borrador.camiones and borrador.kg_por_camion:
        return borrador.camiones * borrador.kg_por_camion
    return KG_MIN_CAMION


def _pedir_camiones(cuenta: Cuenta, borrador: Borrador, libres: int, aviso: str = "") -> Respuesta:
    assert borrador.fecha is not None and borrador.sede is not None
    texto = (
        f"{NOMBRE_SEDE[borrador.sede]}, {dia_largo(borrador.fecha)}: "
        f"quedan {toneladas(libres)} libres.\n"
        f"¿Cuántos camiones vas a mandar? Escribí un número del 1 al {CAMIONES_MAX}."
    )
    return Respuesta(
        texto=f"{aviso}\n{texto}" if aviso else texto,
        estado=_estado_turno(cuenta, TURNO_CAMIONES, borrador),
    )


def _pedir_kg(cuenta: Cuenta, borrador: Borrador, aviso: str = "") -> Respuesta:
    sugerido = borrador.kg_sugerido or KG_POR_DEFECTO
    texto = (
        f"¿Cuántos kilos trae cada camión, más o menos? Calculamos {miles(sugerido)} kg.\n"
        f"Si es otro valor, escribilo (entre {miles(KG_MIN_CAMION)} y "
        f"{miles(KG_MAX_CAMION)} kg)."
    )
    return Respuesta(
        texto=f"{aviso}\n{texto}" if aviso else texto,
        opciones=[f"Sí, {miles(sugerido)} kg por camión"],
        estado=_estado_turno(cuenta, TURNO_KG, replace(borrador, kg_sugerido=sugerido)),
    )


def _pedir_organica(cuenta: Cuenta, borrador: Borrador, aviso: str = "") -> Respuesta:
    texto = "¿La uva de estos camiones es orgánica?"
    return Respuesta(
        texto=f"{aviso}\n{texto}" if aviso else texto,
        opciones=["Sí, orgánica", "No"],
        estado=_estado_turno(cuenta, TURNO_ORGANICA, borrador),
    )


def _resumen(cuenta: Cuenta, borrador: Borrador, aviso: str = "") -> Respuesta:
    assert borrador.sede and borrador.fecha and borrador.camiones and borrador.kg_por_camion
    total = borrador.camiones * borrador.kg_por_camion
    camiones = "camión" if borrador.camiones == 1 else "camiones"
    texto = (
        "Revisá el pedido:\n"
        f"Cuenta: {_nombre(cuenta)} ({cuenta.codigo})\n"
        f"Bodega: {NOMBRE_SEDE[borrador.sede]}\n"
        f"Día: {dia_largo(borrador.fecha)}\n"
        f"Camiones: {borrador.camiones} {camiones} de {miles(borrador.kg_por_camion)} kg "
        f"({miles(total)} kg en total)\n"
        f"Uva orgánica: {'sí' if borrador.organica else 'no'}\n"
        "¿Pido el turno?"
    )
    return Respuesta(
        texto=f"{aviso}\n{texto}" if aviso else texto,
        opciones=["Sí, pedir el turno", "No, cancelar"],
        estado=_estado_turno(cuenta, TURNO_CONFIRMAR, borrador),
    )


def _despues_del_dia(cuenta: Cuenta, borrador: Borrador, libres: int, ctx: _Contexto) -> Respuesta:
    # Si vuelve a elegir día después de un rechazo, no se le preguntan de nuevo los camiones.
    if borrador.camiones and borrador.kg_por_camion:
        return _despues_de_los_kilos(cuenta, borrador, ctx)
    return _pedir_camiones(cuenta, borrador, libres)


def _despues_de_los_kilos(cuenta: Cuenta, borrador: Borrador, ctx: _Contexto) -> Respuesta:
    assert ctx.turnos is not None and borrador.fecha is not None
    if ctx.turnos.tiene_organico(cuenta.clientecuit, borrador.fecha):
        return _pedir_organica(cuenta, borrador)
    return _resumen(cuenta, replace(borrador, organica=False))


def _elegir_fecha(
    cuenta: Cuenta, borrador: Borrador, fecha: date, ctx: _Contexto
) -> Respuesta:
    assert ctx.turnos is not None and borrador.sede is not None
    hoy = ctx.hoy_turnos
    sede = NOMBRE_SEDE[borrador.sede]
    if fecha < hoy:
        return _pedir_dia(cuenta, borrador, ctx, "Ese día ya pasó.")
    if fecha > hoy + timedelta(days=DIAS_MAXIMOS):
        return _pedir_dia(
            cuenta, borrador, ctx,
            f"Los turnos se piden con hasta {DIAS_MAXIMOS} días de anticipación.",
        )
    libres = ctx.turnos.libres(borrador.sede, fecha, fecha).get(fecha)
    if libres is None:
        return _pedir_dia(
            cuenta, borrador, ctx,
            f"Para el {dia_largo(fecha)} la bodega todavía no definió el cupo de {sede}.",
        )
    if libres < KG_MIN_CAMION:
        return _pedir_dia(
            cuenta, borrador, ctx, f"El {dia_largo(fecha)} ya no queda lugar en {sede}."
        )
    if libres < _kilos_necesarios(borrador):
        return _pedir_dia(
            cuenta, borrador, ctx,
            f"El {dia_largo(fecha)} quedan {toneladas(libres)} libres en {sede}: "
            "no alcanza para tu pedido.",
        )
    return _despues_del_dia(cuenta, replace(borrador, fecha=fecha, dias=()), libres, ctx)


def _paso_turno(
    texto: str | None, t: str, cuenta: Cuenta, paso: str, borrador: Borrador, ctx: _Contexto
) -> Respuesta:
    assert ctx.turnos is not None
    if paso == TURNO_SEDE or borrador.sede is None:
        indice = _opcion_elegida(t, [nombre for _, nombre in SEDES])
        if indice is None:
            return _pedir_sede(cuenta, "No entendí la bodega." if paso == TURNO_SEDE else "")
        return _pedir_dia(cuenta, Borrador(sede=SEDES[indice][0]), ctx)

    if paso == TURNO_DIA or borrador.fecha is None:
        opciones = [str(i) for i in range(1, len(borrador.dias) + 2)]
        if t in opciones and int(t) == len(borrador.dias) + 1 or t == "otra bodega":
            return _pedir_sede(cuenta)
        if t in opciones:
            return _elegir_fecha(cuenta, borrador, borrador.dias[int(t) - 1], ctx)
        fecha = fecha_escrita(texto, ctx.hoy_turnos)
        if fecha is None:
            return _pedir_dia(cuenta, borrador, ctx, "No entendí el día.")
        return _elegir_fecha(cuenta, borrador, fecha, ctx)

    if paso == TURNO_CAMIONES:
        camiones = entero_escrito(texto)
        if camiones is None or not 1 <= camiones <= CAMIONES_MAX:
            libres = ctx.turnos.libres(borrador.sede, borrador.fecha, borrador.fecha).get(
                borrador.fecha, 0
            )
            return _pedir_camiones(
                cuenta, borrador, libres, f"Tiene que ser un número entre 1 y {CAMIONES_MAX}."
            )
        sugerido = min(max(ctx.turnos.kg_estimado(cuenta.clientecuit), KG_MIN_CAMION), KG_MAX_CAMION)
        return _pedir_kg(cuenta, replace(borrador, camiones=camiones, kg_sugerido=sugerido))

    if paso == TURNO_KG:
        if t == "1" or t in _SI or t.startswith("si,"):
            kilos: int | None = borrador.kg_sugerido or KG_POR_DEFECTO
        else:
            kilos = kilos_escritos(texto)
        if kilos is None or not KG_MIN_CAMION <= kilos <= KG_MAX_CAMION:
            return _pedir_kg(cuenta, borrador, "No me cerró ese valor.")
        return _despues_de_los_kilos(cuenta, replace(borrador, kg_por_camion=kilos), ctx)

    if paso == TURNO_ORGANICA:
        indice = _opcion_elegida(t, ["Sí, orgánica", "No"])
        if indice == 0 or t in _SI or t == "organica":
            return _resumen(cuenta, replace(borrador, organica=True))
        if indice == 1 or t in _NO or t.startswith("no "):
            return _resumen(cuenta, replace(borrador, organica=False))
        return _pedir_organica(cuenta, borrador, "Respondé 1 (sí) o 2 (no).")

    if paso == TURNO_CONFIRMAR:
        indice = _opcion_elegida(t, ["Sí, pedir el turno", "No, cancelar"])
        if indice == 1 or t in _NO:
            return _menu(cuenta, ctx, "Listo, no pedí ningún turno.")
        if indice != 0 and t not in _SI:
            return _resumen(cuenta, borrador, "Respondé 1 para pedir el turno o 2 para cancelar.")
        return _reservar(cuenta, borrador, ctx)

    return _menu(cuenta, ctx)


def _reservar(cuenta: Cuenta, borrador: Borrador, ctx: _Contexto) -> Respuesta:
    assert ctx.turnos is not None
    assert borrador.sede and borrador.fecha and borrador.camiones and borrador.kg_por_camion
    try:
        turno = ctx.turnos.reservar(
            cuenta.clientecuit,
            cuenta.codigo,
            borrador.sede,
            borrador.fecha,
            borrador.camiones,
            borrador.kg_por_camion,
            bool(borrador.organica),
        )
    except TurnoRechazado as exc:
        aviso = f"No pude pedir el turno: {motivo_en_palabras(str(exc))}\nElegí otro día."
        return _pedir_dia(cuenta, borrador, ctx, aviso)
    camiones = "camión" if turno.camiones == 1 else "camiones"
    aviso = (
        f"¡Listo! Turno N° {turno.id} pedido.\n"
        f"{NOMBRE_SEDE.get(turno.sede, turno.sede)}, {dia_largo(turno.fecha)}: "
        f"{turno.camiones} {camiones} de {miles(turno.kg_por_camion)} kg"
        + (", uva orgánica" if turno.organica else "")
        + '.\nLo podés ver cuando quieras en "Mis turnos".'
    )
    return _menu(cuenta, ctx, aviso)


def _mis_turnos(elegida: Cuenta, ctx: _Contexto) -> Respuesta:
    assert ctx.turnos is not None
    hoy = ctx.hoy_turnos
    proximos = ctx.turnos.proximos([c.clientecuit for c in ctx.cuentas_turno], hoy)
    if not proximos:
        return _menu(elegida, ctx, "No tenés turnos pedidos de hoy en adelante.")
    varias = len(ctx.cuentas_turno) > 1
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
    return _menu(elegida, ctx, "Tus próximos turnos:\n" + "\n".join(lineas))
