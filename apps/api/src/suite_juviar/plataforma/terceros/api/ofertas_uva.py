"""Ofertas de uva de la temporada y asignación de días por la bodega.

El productor ofrece por WhatsApp los kilos de cada variedad para toda la temporada (o
la bodega los carga acá). La bodega revisa cada oferta contra lo que entregó en los
últimos años y le asigna los días corridos, sin domingos. Al asignar se crean los turnos
de cada día (los que ven el guardia y Báscula) y el bot le avisa al productor.

El reparto día por día y los textos de los avisos se arman acá (funciones puras, con
pruebas); la base sólo comprueba que el reparto sea válido (infra/038).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .tablero_fila import ZONA, GestionaTurnos, _escribir, _leer, _sede_valida, buscar_productores

router = APIRouter(prefix="/turnos-bodega/ofertas", tags=["turnos de cosecha"])

MES_INICIO_COSECHA = 12  # la temporada 2027 empieza el 1/12/2026 (igual que el bot)
KG_MIN_CAMION, KG_MAX_CAMION, KG_CAMION_DEFECTO = 1_000, 40_000, 11_000
CAMIONES_MAX = 50
NOMBRES = {"chimbas": "Chimbas", "lavalle": "Lavalle", "media-agua": "Media Agua"}
_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def hoy() -> date:
    return datetime.now(ZONA).date()


def temporada_de_oferta(dia: date) -> int:
    """Igual que la base: lo ofrecido de junio en adelante es para la cosecha siguiente."""
    return dia.year + 1 if dia.month >= 6 else dia.year


def miles(valor: float) -> str:
    return f"{round(valor):,}".replace(",", ".")


def dia_largo(dia: date) -> str:
    return f"{_DIAS[dia.weekday()]} {dia:%d/%m}"


# --- Reparto de los días ----------------------------------------------------------------


def dias_habiles(inicio: date, cantidad: int) -> list[date]:
    """Días corridos desde ``inicio`` salteando los domingos."""
    dias, dia = [], inicio
    while len(dias) < cantidad:
        if dia.weekday() != 6:
            dias.append(dia)
        dia += timedelta(days=1)
    return dias


def repartir(kg: int, kg_dia: int, inicio: date, kg_camion: int) -> list[dict[str, Any]]:
    """Kilos de cada día: ``kg_dia`` por día y el resto el último. Si lo que sobra no llega
    a un camión, se suma al día anterior. Cada día se arma con camiones enteros."""
    if kg_dia < KG_MIN_CAMION:
        raise ValueError("Los kilos por día tienen que ser al menos 1.000.")
    kg_camion = min(max(kg_camion, KG_MIN_CAMION), KG_MAX_CAMION)
    cantidad = max(1, math.ceil(kg / kg_dia))
    por_dia = [kg_dia] * (cantidad - 1) + [kg - kg_dia * (cantidad - 1)]
    if len(por_dia) > 1 and por_dia[-1] < KG_MIN_CAMION:
        resto = por_dia.pop()
        por_dia[-1] += resto
    reparto = []
    for dia, kilos in zip(dias_habiles(inicio, len(por_dia)), por_dia, strict=True):
        camiones = max(1, math.ceil(kilos / kg_camion))
        if camiones > CAMIONES_MAX:
            raise ValueError(f"Un día necesita más de {CAMIONES_MAX} camiones: bajá los kilos por día.")
        por_camion = math.ceil(kilos / camiones)
        por_camion = max(por_camion, KG_MIN_CAMION)
        reparto.append({"fecha": dia, "kg": kilos, "camiones": camiones, "kg_por_camion": por_camion})
    return reparto


def con_capacidad(reparto: list[dict[str, Any]], capacidad: dict[date, int | None],
                  reservado: dict[date, int]) -> list[dict[str, Any]]:
    """Agrega lo libre de cada día y cuánto se pasaría. Pasarse no impide asignar."""
    dias = []
    for d in reparto:
        cap = capacidad.get(d["fecha"])
        libre = None if cap is None else cap - reservado.get(d["fecha"], 0)
        exceso = 0 if libre is None else max(0, d["camiones"] * d["kg_por_camion"] - max(libre, 0))
        dias.append({**d, "libre_kg": libre, "exceso_kg": exceso})
    return dias


# --- Historial y alertas ----------------------------------------------------------------


def resumir_historial(entregas: list[dict[str, Any]], de_temporada: int, anios: int) -> dict[str, Any]:
    """Kilos por temporada en los ``anios`` anteriores a la de la oferta.

    ``entregas`` trae una fila por temporada y variedad: temporada, variedad, kg, desde, hasta.
    """
    temporadas = list(range(de_temporada - anios, de_temporada))
    por_anio = []
    for t in temporadas:
        filas = [e for e in entregas if e["temporada"] == t]
        kg = sum(int(e["kg"] or 0) for e in filas)
        por_anio.append({
            "temporada": t,
            "kg": kg,
            "desde": min((e["desde"] for e in filas), default=None),
            "hasta": max((e["hasta"] for e in filas), default=None),
            "variedades": sorted(({"variedad": e["variedad"], "kg": int(e["kg"] or 0)} for e in filas),
                                 key=lambda v: -v["kg"]),
        })
    con_entregas = [a for a in por_anio if a["kg"] > 0]
    promedio = round(sum(a["kg"] for a in con_entregas) / len(con_entregas)) if con_entregas else None
    return {"anios": por_anio, "anios_con_entregas": len(con_entregas), "promedio_kg": promedio,
            "entrego_ultimo": bool(por_anio and por_anio[-1]["kg"] > 0)}


def constancia(historial: dict[str, Any], anios: int) -> str:
    """Para priorizar en años de sobreoferta."""
    n = historial["anios_con_entregas"]
    if n == 0:
        return "nuevo"
    if n == anios:
        return "constante"
    if n == 1 and historial["entrego_ultimo"]:
        return "solo_ultimo"
    return "algunos"


def sobreoferta(ofrecido_kg: int, promedio_kg: int | None, tolerancia: int) -> int:
    """Kilos por encima del promedio histórico más la tolerancia; 0 si no se pasa."""
    if not promedio_kg:
        return 0
    return max(0, ofrecido_kg - round(promedio_kg * (100 + tolerancia) / 100))


# --- Textos para el productor -----------------------------------------------------------


def aviso_asignacion(productor: str, sede: str, variedad: str, reparto: list[dict[str, Any]]) -> str:
    desde, hasta = reparto[0]["fecha"], reparto[-1]["fecha"]
    lineas = [f"• {dia_largo(d['fecha'])}: {d['camiones']} {'camión' if d['camiones'] == 1 else 'camiones'}"
              f" ({miles(d['camiones'] * d['kg_por_camion'])} kg)" for d in reparto]
    if len(lineas) > 12:
        lineas = lineas[:11] + [f"• … y {len(reparto) - 11} días más"]
    return (f"Hola, {productor}. La bodega {NOMBRES.get(sede, sede)} te asignó los días para tu {variedad}:\n"
            f"del {dia_largo(desde)} al {dia_largo(hasta)} (sin domingos).\n" + "\n".join(lineas)
            + '\nLo podés ver cuando quieras en "Mis turnos".')


def aviso_detencion(productor: str, sede: str, variedad: str, hasta: date) -> str:
    return (f"Hola, {productor}. La bodega {NOMBRES.get(sede, sede)} postergó tu {variedad} porque "
            f"todavía le falta grado. Te vamos a asignar días nuevos a partir del {dia_largo(hasta)}.")


# --- Lecturas -----------------------------------------------------------------------------


def _parametros() -> dict[str, Any]:
    filas = _leer("SELECT anios_historial, tolerancia_sobreoferta, kg_dia_sugerido, semanas_stop "
                  "FROM fila.parametro_ofertas WHERE id = 1", {})
    if not filas:
        raise HTTPException(503, "Falta aplicar la actualización de ofertas en la base de la fila.")
    return filas[0]


def _entregas(cuits: list[str], desde: date) -> dict[str, list[dict[str, Any]]]:
    if not cuits:
        return {}
    filas = _leer(
        """SELECT clientecuit,
                  extract(year FROM fecha + interval '1 month')::int AS temporada,
                  COALESCE(NULLIF(btrim(variedad), ''), 'Sin variedad') AS variedad,
                  sum(neto) AS kg, min(fecha)::date AS desde, max(fecha)::date AS hasta
             FROM consulta.descarga_publica
            WHERE clientecuit = ANY(%(cuits)s) AND estado = 'descargado' AND neto > 0
              AND fecha >= %(desde)s
            GROUP BY 1, 2, 3""",
        {"cuits": cuits, "desde": desde},
    )
    por_cuit: dict[str, list[dict[str, Any]]] = {}
    for f in filas:
        por_cuit.setdefault(f["clientecuit"], []).append(f)
    return por_cuit


def _kg_camion(cuits: list[str]) -> dict[str, int]:
    """Lo que trae un camión de cada productor, por sus últimas descargas."""
    if not cuits:
        return {}
    filas = _leer(
        """SELECT clientecuit, round(avg(neto), -2)::int AS kg FROM (
               SELECT clientecuit, neto, row_number() OVER (PARTITION BY clientecuit ORDER BY fecha DESC) n
                 FROM consulta.descarga_publica
                WHERE clientecuit = ANY(%(cuits)s) AND estado = 'descargado' AND neto > 0) u
            WHERE n <= 30 GROUP BY 1""",
        {"cuits": cuits},
    )
    return {f["clientecuit"]: min(max(f["kg"], KG_MIN_CAMION), KG_MAX_CAMION) for f in filas}


def _inicio_temporada(t: int) -> date:
    return date(t - 1, MES_INICIO_COSECHA, 1)


ESTADOS = ("pendiente", "asignada", "detenida", "desestimada")


@router.get("")
def listar(_: GestionaTurnos, sede: str, temporada: int | None = Query(default=None, ge=2000, le=2100)):
    _sede_valida(sede)
    t = temporada or temporada_de_oferta(hoy())
    p = _parametros()
    anios = p["anios_historial"]
    ofertas = _leer(
        """SELECT o.id, o.pedido, o.clientecuit, o.clientecodigo, o.variedad, o.kg, o.kg_a_programar,
                  o.organica, o.canal, o.pedido_por, o.estado, o.kg_dia, o.detenida_hasta, o.motivo,
                  o.creado_en, p.razonsocial, p.alta_preliminar_por, r.kg_dia AS ritmo,
                  (SELECT min(fecha) FROM fila.turno t WHERE t.oferta_id = o.id AND t.estado = 'activo') AS desde,
                  (SELECT max(fecha) FROM fila.turno t WHERE t.oferta_id = o.id AND t.estado = 'activo') AS hasta,
                  (SELECT count(*) FROM fila.turno t WHERE t.oferta_id = o.id AND t.estado = 'activo') AS dias,
                  (SELECT max(enviado_en) FROM fila.aviso_productor a WHERE a.oferta_id = o.id) AS avisado_en,
                  (SELECT count(*) FROM fila.aviso_productor a WHERE a.oferta_id = o.id AND a.enviado_en IS NULL)
                      AS avisos_pendientes
             FROM fila.oferta o
             JOIN fila.productor p ON p.clientecuit = o.clientecuit
             LEFT JOIN fila.ritmo_productor r ON r.clientecuit = o.clientecuit AND r.sede = o.sede
            WHERE o.sede = %(sede)s AND o.temporada = %(temporada)s
            ORDER BY o.creado_en""",
        {"sede": sede, "temporada": t},
    )
    cuits = sorted({o["clientecuit"] for o in ofertas})
    entregas = _entregas(cuits, _inicio_temporada(t - anios))
    # Lo ofrecido por cada productor en la temporada, todas las variedades que siguen en pie.
    ofrecido: dict[str, int] = {}
    for o in ofertas:
        if o["estado"] != "desestimada":
            ofrecido[o["clientecuit"]] = ofrecido.get(o["clientecuit"], 0) + int(o["kg"])
    resultado = []
    for o in ofertas:
        historial = resumir_historial(entregas.get(o["clientecuit"], []), t, anios)
        # Los kilos por día los fija la bodega; si todavía no los cargó, se estima con el sugerido.
        ritmo = o["kg_dia"] or o["ritmo"] or p["kg_dia_sugerido"]
        resultado.append({
            "id": o["id"], "cuit": o["clientecuit"], "codigo": o["clientecodigo"],
            "productor": o["razonsocial"], "productor_nuevo": bool(o["alta_preliminar_por"]),
            "variedad": o["variedad"], "kg": o["kg"], "kg_a_programar": o["kg_a_programar"],
            "organica": o["organica"], "canal": o["canal"], "pedido_por": o["pedido_por"],
            "estado": o["estado"], "motivo": o["motivo"], "detenida_hasta": o["detenida_hasta"],
            "creado_en": o["creado_en"], "kg_dia": ritmo, "kg_dia_propio": bool(o["kg_dia"] or o["ritmo"]),
            "dias_estimados": math.ceil(o["kg_a_programar"] / ritmo),
            "desde": o["desde"], "hasta": o["hasta"], "dias": o["dias"],
            "avisado_en": o["avisado_en"], "avisos_pendientes": o["avisos_pendientes"],
            "historial": historial,
            "constancia": constancia(historial, anios),
            "ofrecido_total_kg": ofrecido.get(o["clientecuit"], 0),
            "sobreoferta_kg": sobreoferta(ofrecido.get(o["clientecuit"], 0), historial["promedio_kg"],
                                          p["tolerancia_sobreoferta"]),
        })
    return {"temporada": t, "parametros": p, "ofertas": resultado}


@router.get("/productores")
def productores(_: GestionaTurnos, q: str = ""):
    return buscar_productores(None, q)


@router.get("/variedades")
def variedades(_: GestionaTurnos):
    filas = _leer(
        """SELECT variedad FROM (
               SELECT btrim(variedad) AS variedad, count(*) AS n FROM consulta.descarga_publica
                WHERE variedad IS NOT NULL AND btrim(variedad) <> '' GROUP BY 1
               UNION ALL
               SELECT btrim(variedad), 0 FROM fila.oferta) v
            GROUP BY variedad ORDER BY max(n) DESC, variedad LIMIT 120""",
        {},
    )
    return [f["variedad"] for f in filas]


# --- Escrituras ---------------------------------------------------------------------------


class OfertaEntrada(BaseModel):
    sede: str
    cuit: str = Field(pattern=r"^\d{11}$")
    nombre_nuevo: str | None = Field(default=None, max_length=120)
    codigo: str | None = Field(default=None, max_length=60)
    variedad: str = Field(min_length=1, max_length=60)
    kg: int = Field(ge=1000, le=50_000_000)
    organica: bool = False


@router.post("", status_code=201)
def cargar(entrada: OfertaEntrada, sesion: GestionaTurnos):
    _sede_valida(entrada.sede)
    return _escribir(
        """SELECT id FROM fila.cargar_oferta_bodega(%(sede)s, %(cuit)s, %(nombre)s, %(codigo)s,
               %(variedad)s, %(kg)s, %(organica)s, %(actor)s)""",
        {"sede": entrada.sede, "cuit": entrada.cuit, "nombre": (entrada.nombre_nuevo or "").strip() or None,
         "codigo": entrada.codigo, "variedad": entrada.variedad.strip(), "kg": entrada.kg,
         "organica": entrada.organica, "actor": sesion.actor},
    )


class AsignarEntrada(BaseModel):
    inicio: date
    kg_dia: int = Field(ge=1000, le=2_000_000)
    kg_por_camion: int | None = Field(default=None, ge=KG_MIN_CAMION, le=KG_MAX_CAMION)


def _oferta(oferta_id: int) -> dict[str, Any]:
    filas = _leer(
        """SELECT o.*, p.razonsocial FROM fila.oferta o JOIN fila.productor p USING (clientecuit)
            WHERE o.id = %(id)s""",
        {"id": oferta_id},
    )
    if not filas:
        raise HTTPException(404, "La oferta no existe.")
    return filas[0]


def _plan(oferta: dict[str, Any], entrada: AsignarEntrada) -> list[dict[str, Any]]:
    if entrada.inicio < hoy():
        raise HTTPException(422, "El primer día tiene que ser de hoy en adelante.")
    kg_camion = entrada.kg_por_camion or _kg_camion([oferta["clientecuit"]]).get(
        oferta["clientecuit"], KG_CAMION_DEFECTO)
    try:
        reparto = repartir(int(oferta["kg_a_programar"]), entrada.kg_dia, entrada.inicio, kg_camion)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    fechas = [d["fecha"] for d in reparto]
    capacidades = _leer("SELECT fecha, kg_dia FROM fila.capacidad WHERE sede = %(sede)s", {"sede": oferta["sede"]})
    defecto = next((c["kg_dia"] for c in capacidades if c["fecha"] is None), None)
    propias = {c["fecha"]: c["kg_dia"] for c in capacidades if c["fecha"] is not None}
    reservas = _leer(
        """SELECT fecha, sum(camiones::bigint * kg_por_camion) AS kg FROM fila.turno
            WHERE sede = %(sede)s AND estado = 'activo' AND fecha = ANY(%(fechas)s) GROUP BY fecha""",
        {"sede": oferta["sede"], "fechas": fechas},
    )
    return con_capacidad(reparto, {f: propias.get(f, defecto) for f in fechas},
                         {r["fecha"]: int(r["kg"]) for r in reservas})


@router.post("/{oferta_id}/vista-previa")
def vista_previa(oferta_id: int, entrada: AsignarEntrada, _: GestionaTurnos):
    oferta = _oferta(oferta_id)
    dias = _plan(oferta, entrada)
    return {"dias": dias, "kg_por_camion": dias[0]["kg_por_camion"] if dias else None,
            "exceso_kg": sum(d["exceso_kg"] for d in dias),
            "aviso": aviso_asignacion(oferta["razonsocial"], oferta["sede"], oferta["variedad"], dias)}


@router.post("/{oferta_id}/asignar")
def asignar(oferta_id: int, entrada: AsignarEntrada, sesion: GestionaTurnos):
    oferta = _oferta(oferta_id)
    dias = _plan(oferta, entrada)
    texto = aviso_asignacion(oferta["razonsocial"], oferta["sede"], oferta["variedad"], dias)
    _escribir(
        """SELECT count(*) AS dias FROM fila.asignar_oferta(%(id)s, %(fechas)s::date[], %(camiones)s::int[],
               %(kg)s::int[], %(kg_dia)s, %(actor)s, %(aviso)s)""",
        {"id": oferta_id, "fechas": [d["fecha"] for d in dias], "camiones": [d["camiones"] for d in dias],
         "kg": [d["kg_por_camion"] for d in dias], "kg_dia": entrada.kg_dia, "actor": sesion.actor,
         "aviso": texto},
    )
    return {"dias": len(dias), "desde": dias[0]["fecha"], "hasta": dias[-1]["fecha"]}


class DetenerEntrada(BaseModel):
    semanas: int = Field(ge=1, le=12)


@router.post("/{oferta_id}/detener")
def detener(oferta_id: int, entrada: DetenerEntrada, sesion: GestionaTurnos):
    oferta = _oferta(oferta_id)
    if entrada.semanas not in _parametros()["semanas_stop"]:
        raise HTTPException(422, "Esa cantidad de semanas no está en los parámetros.")
    hasta = hoy() + timedelta(weeks=entrada.semanas)
    _escribir("SELECT id FROM fila.detener_oferta(%(id)s, %(hasta)s, %(actor)s, %(aviso)s)",
              {"id": oferta_id, "hasta": hasta, "actor": sesion.actor,
               "aviso": aviso_detencion(oferta["razonsocial"], oferta["sede"], oferta["variedad"], hasta)})
    return {"hasta": hasta}


class DesestimarEntrada(BaseModel):
    motivo: str = Field(min_length=3, max_length=300)


@router.post("/{oferta_id}/desestimar")
def desestimar(oferta_id: int, entrada: DesestimarEntrada, sesion: GestionaTurnos):
    return _escribir("SELECT id, estado FROM fila.desestimar_oferta(%(id)s, %(motivo)s, %(actor)s)",
                     {"id": oferta_id, "motivo": entrada.motivo.strip(), "actor": sesion.actor})


class ParametrosEntrada(BaseModel):
    anios_historial: int = Field(ge=1, le=10)
    tolerancia_sobreoferta: int = Field(ge=0, le=500)
    kg_dia_sugerido: int = Field(ge=1000, le=2_000_000)
    semanas_stop: list[int] = Field(min_length=1, max_length=8)


@router.put("/parametros")
def fijar_parametros(entrada: ParametrosEntrada, sesion: GestionaTurnos):
    return _escribir(
        """SELECT anios_historial, tolerancia_sobreoferta, kg_dia_sugerido, semanas_stop
             FROM fila.fijar_parametro_ofertas(%(a)s, %(t)s, %(k)s, %(s)s::int[], %(actor)s)""",
        {"a": entrada.anios_historial, "t": entrada.tolerancia_sobreoferta, "k": entrada.kg_dia_sugerido,
         "s": entrada.semanas_stop, "actor": sesion.actor},
    )
