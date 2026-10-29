"""Carga de demostración para una instalación nueva de Gestión.

Llena las secciones con un uso verosímil de los últimos cuatro meses: entregas de
EPP firmadas, capacitaciones, certificados médicos, búsquedas con CV, adjuntos de
legajo y cronogramas de Bodega. Todas las personas son ficticias.

Sólo usa la API pública, dentro del mismo proceso, para que rijan las reglas de
negocio. No abre ningún puerto. Requiere SJ_ENTORNO=prueba y las rutas SQLite:

    SJ_MODULOS_SQLITE_PATH, SJ_RRHH_EPP_SQLITE_PATH, SJ_RECEPCION_SQLITE_PATH

Es idempotente: deja la marca `.demostracion_cargada` junto a SJ_MODULOS_SQLITE_PATH
y, si la encuentra (o ya hay capacitaciones cargadas), no hace nada.

    python tools/cargar_demostracion.py
"""

from __future__ import annotations

import base64
import json
import math
import os
import random
import sys
from datetime import UTC, date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

ZONA = ZoneInfo("America/Argentina/San_Juan")
AZAR = random.Random(20261028)
DIAS_HISTORIA = 118

# Quién opera cada pantalla. Son nombres de fantasía, como el resto de los datos, y sin
# tildes: viajan en cabeceras HTTP, que sólo admiten ASCII sin recodificar.
ACTOR_RRHH = "Gabriela Mercado"
ACTOR_HYS = "Paula Echegaray"
ACTOR_MEDICO = "Dr. Sergio Lorenzo Bravo"
ACTOR_DEPOSITO = "Mauricio Torres"
ACTOR_SUPERVISOR = "Osvaldo Atencio"
OPERADOR_PANOL = {"ENAV": "1192", "JUBIAR": "1210"}


# --------------------------------------------------------------------------
# Entorno y marca de carga
# --------------------------------------------------------------------------


def ruta_marca() -> Path:
    ruta = os.getenv("SJ_MODULOS_SQLITE_PATH", "").strip()
    if not ruta:
        sys.exit("Falta SJ_MODULOS_SQLITE_PATH: no sé dónde está la base de Gestión.")
    return Path(ruta).resolve().parent / ".demostracion_cargada"


def verificar_entorno() -> None:
    entorno = (os.getenv("SJ_ENTORNO") or os.getenv("ENTORNO") or "").lower()
    if entorno != "prueba":
        sys.exit("La carga de demostración sólo corre con SJ_ENTORNO=prueba.")
    faltantes = [
        clave for clave in ("SJ_RRHH_EPP_SQLITE_PATH", "SJ_RECEPCION_SQLITE_PATH")
        if not os.getenv(clave, "").strip()
    ]
    if faltantes:
        sys.exit(f"Faltan variables de entorno: {', '.join(faltantes)}.")
    # Las cabeceras de identidad simulada sólo valen dentro de este proceso,
    # que no escucha en ningún puerto; el servidor sigue con su ingreso real.
    os.environ.pop("SJ_IDENTIDAD_REAL", None)


# --------------------------------------------------------------------------
# Documentos: firma manuscrita, certificados, CV y adjuntos
# --------------------------------------------------------------------------


def firma_png(semilla: str, ancho: int = 360, alto: int = 120) -> bytes:
    """Trazo cursivo con letras de alto y bucle irregulares, más la rúbrica."""
    azar = random.Random(semilla)
    imagen = Image.new("RGB", (ancho, alto), "white")
    dibujo = ImageDraw.Draw(imagen)
    tinta = (22, 32, 78)
    # Una "letra" cada ~18 px: alto, ancho del bucle y vaivén de la línea base.
    largo = azar.uniform(0.5, 0.75) * ancho
    mayusculas = {0, azar.randint(4, 7)}
    letras = [(azar.uniform(5, 15) * (2.2 if i in mayusculas else 1),
               azar.choice((0.2, 0.5, 1.0, 1.3)), azar.uniform(-5, 5))
              for i in range(int(largo / 18) + 2)]
    inclinacion = azar.uniform(0.15, 0.35)
    puntos = []
    t = 0.0
    while t < largo:
        i, f = int(t / 18), (t % 18) / 18
        mezcla = [a * (1 - f) + b * f for a, b in zip(letras[i], letras[i + 1])]
        altura, bucle, base = mezcla
        angulo = t * 2 * math.pi / 18
        y = alto * 0.5 + base - altura * math.sin(angulo) - t * 0.06
        x = 26 + t + altura * bucle * 0.55 * math.cos(angulo) + (alto * 0.5 - y) * inclinacion
        puntos.append((x, y))
        t += 0.5
    dibujo.line(puntos, fill=tinta, width=3, joint="curve")
    # Rúbrica: una curva de Bézier que vuelve por debajo del nombre.
    (x0, y0), x1 = puntos[-1], azar.uniform(0.3, 0.6) * largo
    control = ((x0 + 45, alto * 0.98), (10, alto * 0.95), (x1, alto * 0.72))
    rubrica = []
    for paso in range(41):
        u = paso / 40
        coef = ((1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u ** 3)
        nodos = ((x0, y0), *control)
        rubrica.append((sum(c * n[0] for c, n in zip(coef, nodos)),
                        sum(c * n[1] for c, n in zip(coef, nodos))))
    dibujo.line(rubrica, fill=tinta, width=2, joint="curve")
    salida = BytesIO()
    imagen.save(salida, format="PNG", optimize=True)
    return salida.getvalue()


def data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def b64(contenido: bytes) -> str:
    return base64.b64encode(contenido).decode("ascii")


def _lienzo(tamano):
    from reportlab.pdfgen.canvas import Canvas

    salida = BytesIO()
    return salida, Canvas(salida, pagesize=tamano)


def pdf_certificado(profesional: dict, persona: dict, diagnostico: str, desde: date,
                    dias: int) -> bytes:
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader

    salida, hoja = _lienzo(A5)
    ancho, alto = A5
    hoja.setTitle("Certificado médico")
    hoja.setFont("Helvetica-Bold", 13)
    hoja.drawString(16 * mm, alto - 20 * mm, profesional["nombre"])
    hoja.setFont("Helvetica", 9)
    hoja.drawString(16 * mm, alto - 25 * mm,
                    f"{profesional['especialidad']} · {profesional['matricula']}")
    hoja.drawString(16 * mm, alto - 29 * mm, profesional["lugar"])
    hoja.line(16 * mm, alto - 32 * mm, ancho - 16 * mm, alto - 32 * mm)
    hoja.setFont("Helvetica-Bold", 12)
    hoja.drawCentredString(ancho / 2, alto - 44 * mm, "CERTIFICADO MÉDICO")
    texto = hoja.beginText(16 * mm, alto - 56 * mm)
    texto.setFont("Helvetica", 10)
    texto.setLeading(15)
    nombre = " ".join(reversed(persona["nombre_completo"].split(", ")))
    for linea in (
        f"Certifico que {nombre}, DNI {persona['dni']},",
        f"fue asistido/a en el día de la fecha y presenta: {diagnostico.lower()}.",
        f"Se indica reposo laboral por {dias} día{'s' if dias > 1 else ''} a partir del",
        f"{desde.strftime('%d/%m/%Y')} inclusive, con control al finalizar.",
        "",
        "Se extiende el presente a pedido del/la interesado/a para ser",
        "presentado ante su empleador.",
    ):
        texto.textLine(linea)
    hoja.drawText(texto)
    hoja.drawString(16 * mm, 52 * mm, f"{profesional['ciudad']}, {desde.strftime('%d/%m/%Y')}")
    firma = ImageReader(BytesIO(firma_png(profesional["nombre"])))
    hoja.drawImage(firma, ancho - 76 * mm, 30 * mm, width=58 * mm, height=19 * mm)
    hoja.setFont("Helvetica", 8)
    hoja.drawCentredString(ancho - 47 * mm, 26 * mm, "Firma y sello")
    hoja.drawCentredString(ancho - 47 * mm, 22 * mm, profesional["matricula"])
    hoja.showPage()
    hoja.save()
    return salida.getvalue()


def pdf_cv(cv: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    salida, hoja = _lienzo(A4)
    ancho, alto = A4
    hoja.setTitle(f"CV {cv['nombre']}")
    hoja.setFont("Helvetica-Bold", 18)
    hoja.drawString(20 * mm, alto - 25 * mm, cv["nombre"])
    hoja.setFont("Helvetica", 11)
    hoja.drawString(20 * mm, alto - 32 * mm, cv["titulo"])
    hoja.line(20 * mm, alto - 36 * mm, ancho - 20 * mm, alto - 36 * mm)
    texto = hoja.beginText(20 * mm, alto - 48 * mm)
    texto.setLeading(17)
    secciones = [
        ("Datos personales", [f"Edad: {cv['edad']} años", f"Localidad: {cv['localidad']}",
                              f"Celular: {cv['celular']}"]),
        ("Formación", [f"Estudios: {cv['estudios']}"] if cv.get("estudios") else []),
        ("Trayectoria", [f"Experiencia: {cv['experiencia']}", *cv["detalle"]]),
        ("Habilidades", [f"Oficio: {cv['oficio']}", *cv.get("extras", [])]),
    ]
    for titulo, lineas in secciones:
        if not lineas:
            continue
        texto.setFont("Helvetica-Bold", 12)
        texto.textLine(titulo)
        texto.setFont("Helvetica", 10)
        for linea in lineas:
            texto.textLine(linea)
        texto.textLine("")
    hoja.drawText(texto)
    hoja.showPage()
    hoja.save()
    return salida.getvalue()


def pdf_constancia_legajo(titulo: str, persona: dict, lineas: list[str], fecha: date) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    salida, hoja = _lienzo(A4)
    ancho, alto = A4
    hoja.setTitle(titulo)
    hoja.setFont("Helvetica-Bold", 12)
    hoja.drawString(20 * mm, alto - 22 * mm, f"{persona['empresa']} · Recursos Humanos")
    hoja.setFont("Helvetica", 9)
    hoja.drawString(20 * mm, alto - 27 * mm, "San Juan, Argentina")
    hoja.line(20 * mm, alto - 30 * mm, ancho - 20 * mm, alto - 30 * mm)
    hoja.setFont("Helvetica-Bold", 14)
    hoja.drawCentredString(ancho / 2, alto - 45 * mm, titulo.upper())
    texto = hoja.beginText(20 * mm, alto - 60 * mm)
    texto.setFont("Helvetica", 10)
    texto.setLeading(16)
    nombre = " ".join(reversed(persona["nombre_completo"].split(", ")))
    for linea in (f"Trabajador/a: {nombre} · Legajo {persona['legajo']} · DNI {persona['dni']}",
                  f"Sector: {persona['sector']} · Puesto: {persona['puesto']}", "", *lineas):
        texto.textLine(linea)
    hoja.drawText(texto)
    hoja.drawString(20 * mm, 40 * mm, f"Fecha: {fecha.strftime('%d/%m/%Y')}")
    hoja.showPage()
    hoja.save()
    return salida.getvalue()


# --------------------------------------------------------------------------
# Cliente de la API
# --------------------------------------------------------------------------


class Api:
    def __init__(self, http) -> None:
        self._http = http

    def __call__(self, metodo: str, ruta: str, perfil: str, *, empresa: str = "ENAV",
                 actor: str | None = None, legajo_usuario: str | None = None,
                 cuerpo: object | None = None):
        cabeceras = {"X-Perfil-Simulado": perfil, "X-Empresa-Simulada": empresa}
        if actor:
            cabeceras["X-Actor-Simulado"] = actor
        if legajo_usuario:
            cabeceras["X-Legajo-Usuario"] = legajo_usuario
        respuesta = self._http.request(metodo, f"/api/v1/{ruta}", headers=cabeceras, json=cuerpo)
        if respuesta.status_code >= 400:
            raise RuntimeError(
                f"{metodo} {ruta} -> {respuesta.status_code}: {respuesta.text[:400]}")
        return respuesta.json()


def momento_laboral(dia: date, desde: float = 7.5, hasta: float = 16.5) -> datetime:
    hora = AZAR.uniform(desde, hasta)
    local = datetime.combine(dia, time(int(hora), int((hora % 1) * 60)), ZONA)
    return local.astimezone(UTC)


def dia_habil(dia: date) -> date:
    while dia.weekday() >= 5:
        dia -= timedelta(days=1)
    return dia


# --------------------------------------------------------------------------
# Secciones
# --------------------------------------------------------------------------


def leer_personas(api: Api) -> list[dict]:
    """Legajos activos con su EPP requerido, tal como los ve el pañol."""
    hys = {"actor": ACTOR_HYS}
    puestos = {p["nombre"]: p["codigo"]
               for p in api("GET", "rrhh-epp/matriz/puestos", "HYS", **hys)}
    sectores = {s["nombre"]: s["codigo"]
                for s in api("GET", "rrhh-epp/matriz/sectores", "HYS", **hys)}
    personas = []
    for fila in api("GET", "legajo/personas", "RRHH", actor=ACTOR_RRHH):
        operador = OPERADOR_PANOL[fila["empresa"]]
        ficha = api("GET", f"rrhh-epp/legajos/{fila['legajo']}", "DEPOSITO",
                    empresa=fila["empresa"], legajo_usuario=operador)
        cabecera = ficha["cabecera"]
        personas.append({**cabecera, "requerido": ficha["epp_requerido"],
                         "puesto_codigo": puestos.get(cabecera["puesto"], ""),
                         "sector_codigo": sectores.get(cabecera["sector"], "")})
    return personas


class Stock:
    """Lleva la cuenta local para no pedir más de lo que hay."""

    def __init__(self, api: Api) -> None:
        self.disponible = {
            fila["item_codigo"]: fila["disponible"]
            for fila in api("GET", "rrhh-epp/stock", "DEPOSITO", actor=ACTOR_DEPOSITO)
        }

    def elegir(self, requisito: dict, cantidad: int) -> str | None:
        items = [i["codigo_interno"] for i in requisito["items"]
                 if self.disponible.get(i["codigo_interno"], 0) >= cantidad]
        if not items:
            return None
        item = AZAR.choice(items[:3])
        self.disponible[item] -= cantidad
        return item


def cargar_epp(api: Api, personas: list[dict], hoy: date) -> int:
    stock = Stock(api)
    # Dos ítems de alta rotación quedan cerca del mínimo: generan el aviso a Compras.
    for item, disponible, minimo in (("SIM-97-01", 34, 30), ("SIM-69-01", 22, 20)):
        if item in stock.disponible:
            api("PUT", f"rrhh-epp/stock/{item}", "DEPOSITO", actor=ACTOR_DEPOSITO,
                cuerpo={"disponible": disponible, "minimo": minimo})
            stock.disponible[item] = disponible

    entregas: list[tuple[datetime, dict, dict]] = []
    temporada_invierno = dia_habil(hoy - timedelta(days=AZAR.randint(108, 114)))
    temporada_verano = dia_habil(hoy - timedelta(days=AZAR.randint(12, 18)))
    for persona in personas:
        requerido = persona["requerido"]
        if not requerido:
            continue
        # Entregas estacionales del convenio: invierno en julio, verano en octubre.
        for inicio, temporadas in ((temporada_invierno, {"INVIERNO"}),
                                   (temporada_verano, {"VERANO", "TODO_EL_ANIO"})):
            if AZAR.random() < 0.12:
                continue  # todavía no retiró
            lineas = [
                (r, r["cantidad_sugerida"]) for r in requerido
                if r["temporada"] in temporadas and r["frecuencia"] in {"SEMESTRAL", "ANUAL"}
            ] if "VERANO" in temporadas else [
                (r, r["cantidad_sugerida"]) for r in requerido if r["temporada"] == "INVIERNO"
            ]
            if lineas:
                dia = dia_habil(inicio + timedelta(days=AZAR.randint(0, 6)))
                entregas.append((momento_laboral(dia), persona, {
                    "circuito": "PROGRAMADA", "motivo": "ENTREGA_ESTACIONAL", "lineas": lineas,
                    "observaciones": "Entrega de temporada según convenio.",
                }))
        # Reposiciones a demanda: guantes, protectores, anteojos.
        a_demanda = [r for r in requerido if r["frecuencia"] == "A_DEMANDA"] or requerido
        for _ in range(AZAR.choice((0, 1, 1, 2, 2, 3))):
            elegidos = AZAR.sample(a_demanda, k=min(len(a_demanda), AZAR.choice((1, 1, 2))))
            motivo = AZAR.choice(("DESGASTE", "DESGASTE", "DESGASTE", "ROTURA"))
            dia = dia_habil(hoy - timedelta(days=AZAR.randint(1, DIAS_HISTORIA)))
            entregas.append((momento_laboral(dia), persona, {
                "circuito": "ESPONTANEA", "motivo": motivo,
                "lineas": [(r, 1 if r["cantidad_sugerida"] < 2 else 2) for r in elegidos],
                "observaciones": "" if motivo == "DESGASTE" else "Se retira el elemento dañado.",
            }))

    cargadas = 0
    for momento, persona, datos in sorted(entregas, key=lambda e: e[0]):
        items = []
        for requisito, cantidad in datos["lineas"]:
            item = stock.elegir(requisito, cantidad)
            if item is None:
                continue
            linea = {"codigo": requisito["codigo"], "item_codigo": item, "cantidad": cantidad}
            if datos["circuito"] == "ESPONTANEA" and AZAR.random() < 0.08:
                linea["reclamo_calidad"] = AZAR.choice(
                    ("DESGASTE_PREMATURO", "TALLE", "MOLESTIA_USO"))
            items.append(linea)
        if not items:
            continue
        api("POST", "rrhh-epp/entregas", "DEPOSITO", empresa=persona["empresa"],
            legajo_usuario=OPERADOR_PANOL[persona["empresa"]], cuerpo={
                "legajo": persona["legajo"], "items": items, "metodo_firma": "TRAZO_TABLET",
                "evidencia_firma": data_url(firma_png(persona["dni"])),
                "observaciones": datos["observaciones"], "entregada_en": momento.isoformat(),
                "circuito": datos["circuito"], "motivo": datos["motivo"],
            })
        cargadas += 1

    # Reposición recibida por Depósito y un ajuste de recuento.
    for item, cantidad, motivo in (
        ("SIM-8-01", 40, "Ingreso por remito 0003-00018452"),
        ("SIM-9-01", 40, "Ingreso por remito 0003-00018452"),
        ("SIM-16-02", 30, "Ingreso por remito 0003-00018517"),
        ("SIM-5-01", 24, "Ingreso por remito 0001-00007731"),
        ("SIM-97-02", -2, "Diferencia en recuento mensual de pañol"),
    ):
        if item in stock.disponible:
            api("POST", f"rrhh-epp/stock/{item}/movimientos", "DEPOSITO", actor=ACTOR_DEPOSITO,
                cuerpo={"cantidad": cantidad, "tipo": "INGRESO" if cantidad > 0 else "AJUSTE",
                        "motivo": motivo})
    return cargadas


TEMAS = (
    ("Uso y manejo de extintores", 2, 12, "Téc. Sup. Hugo Albarracín",
     {"BOD", "ENV", "PAN", "CAL", "LAG", "PRE", "MAE"}),
    ("Manejo seguro de autoelevadores", 4, 24, "Ing. Martín Cabrera", {"OP-AUT", "OP-PAN"}),
    ("Primeros auxilios y RCP", 3, 12, "Lic. Enf. Carolina Vidable",
     {"VIN", "BOD", "ADM", "LAB", "BAS"}),
    ("Trabajo en altura", 4, 12, "Téc. HyS Paula Echegaray", {"MEC", "ELE", "COL", "CON"}),
    ("Manipulación segura de productos químicos", 2, 12, "Ing. Laura Bazán",
     {"CLA", "FIL", "FVA", "EFL", "LIM", "LAB"}),
    ("Orden y limpieza 5S", 1.5, None, "Ing. Diego Fuentes", {"ENV", "PAN", "BOD", "MAE"}),
    ("Ingreso a espacios confinados en vasijas", 3, 12, "Téc. HyS Paula Echegaray",
     {"LAG", "BOD", "PRE"}),
)


def cargar_capacitaciones(api: Api, personas: list[dict], hoy: date) -> tuple[int, int, int]:
    rrhh = {"actor": ACTOR_RRHH}
    dictados = asistencias = 0
    for indice, (nombre, horas, periodicidad, instructor, alcance) in enumerate(TEMAS):
        tema = api("POST", "capacitaciones/temas", "RRHH", **rrhh, cuerpo={
            "nombre": nombre, "horas": horas, "periodicidad_meses": periodicidad})
        alcanzados = [p for p in personas
                      if p["sector_codigo"] in alcance or p["puesto_codigo"] in alcance]
        por_puesto = any(codigo.startswith("OP-") for codigo in alcance)
        mitad = len(alcanzados) // 2 + 1
        grupos = [alcanzados[:mitad], alcanzados[mitad:]] if len(alcanzados) > 6 else [alcanzados]
        for numero, grupo in enumerate(g for g in grupos if g):
            dia = dia_habil(hoy - timedelta(days=100 - indice * 12 - numero * 9))
            dictado = api("POST", "capacitaciones/dictados", "RRHH", **rrhh, cuerpo={
                "tema_id": tema["id"], "fecha": dia.isoformat(), "instructor": instructor,
                "duracion_horas": horas,
                "convocatoria_tipo": "PUESTO" if por_puesto else "SECTOR",
                "convocatoria_detalle": ", ".join(sorted({p["sector"] for p in grupo}))
                if not por_puesto else "Autoelevadoristas y personal de pañol",
                "convocados": [p["legajo"] for p in grupo],
            })
            dictados += 1
            for persona in grupo:
                suerte = AZAR.random()
                if suerte < 0.08:
                    continue  # no asistió y no se lo registró
                presente = suerte >= 0.13
                tablet = presente and suerte >= 0.2
                api("POST", f"capacitaciones/dictados/{dictado['id']}/asistencias", "RRHH",
                    **rrhh, cuerpo={
                        "legajo": persona["legajo"], "nombre_completo": persona["nombre_completo"],
                        "presente": presente,
                        "supervisor": persona["puesto_codigo"] == "CAP-VIN",
                        "metodo_firma": "TRAZO_TABLET" if tablet else None,
                        "evidencia_firma": data_url(firma_png(persona["dni"])) if tablet else None,
                    })
                asistencias += 1
            if numero == 0 and indice == 0 and len(grupo) > 2:
                api("POST", f"capacitaciones/dictados/{dictado['id']}/asistencias/"
                    f"{grupo[-1]['legajo']}/anular", "RRHH", **rrhh,
                    cuerpo={"motivo": "Cargado por error: asistió al dictado del turno tarde."})
    return len(TEMAS), dictados, asistencias


PROFESIONALES = (
    {"nombre": "Dra. María José Ferrer", "especialidad": "Médica clínica",
     "matricula": "M.P. 3418", "lugar": "Consultorio particular · Rawson", "ciudad": "Rawson"},
    {"nombre": "Dr. Gonzalo Iturrieta", "especialidad": "Traumatología y ortopedia",
     "matricula": "M.P. 2975", "lugar": "Consultorio de traumatología · Capital",
     "ciudad": "San Juan"},
    {"nombre": "Dra. Valeria Castañeda", "especialidad": "Medicina general y familiar",
     "matricula": "M.P. 4102", "lugar": "Centro de atención primaria · Pocito",
     "ciudad": "Pocito"},
    {"nombre": "Dr. Sebastián Orellano", "especialidad": "Gastroenterología",
     "matricula": "M.P. 3661", "lugar": "Consultorio de especialidades · Rivadavia",
     "ciudad": "Rivadavia"},
    {"nombre": "Dra. Lorena Paredes", "especialidad": "Oftalmología",
     "matricula": "M.P. 3890", "lugar": "Consultorio oftalmológico · Capital",
     "ciudad": "San Juan"},
)

CERTIFICADOS = (
    # diagnóstico, profesional, días, accidente, resumen para sueldos
    ("RESP-GRIPE", 0, 3, "NO_ES_ACCIDENTE", "Reposo por cuadro gripal."),
    ("RESP-GRIPE", 2, 2, "NO_ES_ACCIDENTE", "Reposo por cuadro gripal."),
    ("RESP-GRIPE", 0, 4, "NO_ES_ACCIDENTE", "Reposo por cuadro gripal."),
    ("RESP-GRIPE", 2, 3, "NO_ES_ACCIDENTE", "Reposo por cuadro gripal."),
    ("RESP-IRA", 0, 2, "NO_ES_ACCIDENTE", "Reposo por infección respiratoria."),
    ("RESP-IRA", 2, 3, "NO_ES_ACCIDENTE", "Reposo por infección respiratoria."),
    ("MUSC-LUMB", 1, 5, "NO_INFORMADO", "Lumbalgia, reposo y control."),
    ("MUSC-LUMB", 1, 7, "ACCIDENTE_A_REVISAR", "Lumbalgia tras levantar cajas en planta."),
    ("MUSC-LUMB", 0, 3, "NO_ES_ACCIDENTE", "Lumbalgia, reposo relativo."),
    ("TRAU-ESG", 1, 10, "ACCIDENTE_LABORAL", "Esguince de tobillo en sector de trabajo."),
    ("TRAU-ESG", 1, 7, "IN_ITINERE", "Esguince al descender del colectivo camino al trabajo."),
    ("DIG-GAST", 3, 2, "NO_ES_ACCIDENTE", "Gastroenteritis aguda."),
    ("DIG-GAST", 2, 2, "NO_ES_ACCIDENTE", "Gastroenteritis aguda."),
    ("TRAU-HER", 2, 4, "ACCIDENTE_LABORAL", "Herida cortante en mano, curación diaria."),
    ("OFT-CONJ", 4, 3, "NO_ES_ACCIDENTE", "Conjuntivitis, reposo para evitar contagio."),
    ("MUSC-TEND", 1, 6, "NO_INFORMADO", "Tendinitis de muñeca, inmovilización."),
    ("NEUR-MIG", 0, 1, "NO_ES_ACCIDENTE", "Episodio de migraña."),
    ("CARD-HTA", 0, 2, "NO_ES_ACCIDENTE", "Control de presión arterial y ajuste de medicación."),
)


def cargar_salud(api: Api, personas: list[dict], hoy: date) -> int:
    catalogo = {d["codigo"]: d["descripcion"]
                for d in api("GET", "salud/catalogo", "MEDICO", actor=ACTOR_MEDICO)["items"]}
    candidatos = [p for p in personas if p["sector_codigo"] != "ADM"] or personas
    elegidos = AZAR.sample(candidatos, k=min(len(candidatos), len(CERTIFICADOS)))
    cargados = 0
    for persona, (codigo, prof, dias, accidente, resumen) in zip(elegidos, CERTIFICADOS):
        if codigo not in catalogo:
            continue
        desde = dia_habil(hoy - timedelta(days=AZAR.randint(dias + 2, DIAS_HISTORIA)))
        hasta = desde + timedelta(days=dias - 1)
        profesional = PROFESIONALES[prof]
        apellido = persona["nombre_completo"].split(",")[0].replace(" ", "_")
        api("POST", "salud/certificados", "MEDICO", empresa=persona["empresa"],
            actor=ACTOR_MEDICO, cuerpo={
                "legajo": persona["legajo"], "diagnostico_codigo": codigo,
                "desde": desde.isoformat(), "hasta": hasta.isoformat(), "dias": dias,
                "profesional": profesional["nombre"],
                "adjunto_nombre": f"certificado_{apellido}_{desde:%Y%m%d}.pdf",
                "adjunto_base64": b64(pdf_certificado(
                    profesional, persona, catalogo[codigo], desde, dias)),
                "resumen": resumen, "tipo_accidente": accidente,
            })
        cargados += 1
    return cargados


BUSQUEDAS = (
    {"nombre": "Operario de bodega · vendimia 2027", "perfil": "BODEGA",
     "edad_minima": 18, "edad_maxima": 45, "secundaria_completa": True},
    {"nombre": "Técnico electromecánico de mantenimiento", "perfil": "MANTENIMIENTO",
     "edad_minima": 21, "edad_maxima": 50, "secundaria_completa": True},
)

CVS = (
    {"nombre": "Lucas Matías Benegas", "titulo": "Operario de bodega", "edad": 27,
     "localidad": "Pocito, San Juan", "celular": "264 15 041-7352",
     "estudios": "Secundario completo (Bachiller en Economía y Gestión)",
     "experiencia": "Operario de bodega durante tres vendimias en establecimiento de Pocito",
     "detalle": ["Trasiegos, limpieza de vasijas y control de temperatura de fermentación."],
     "oficio": "Operario de bodega, autoelevador con carnet vigente"},
    {"nombre": "Daiana Belén Mallea", "titulo": "Auxiliar de enología", "edad": 24,
     "localidad": "Rawson, San Juan", "celular": "264 15 062-1984",
     "estudios": "Secundario completo; cursando Tecnicatura en Enología",
     "experiencia": "Auxiliar de laboratorio y bodega en cooperativa vitivinícola (2 años)",
     "detalle": ["Toma de muestras, análisis de rutina y registro de lotes."],
     "oficio": "Enología y control de procesos de bodega"},
    {"nombre": "Ramiro Nahuel Guevara", "titulo": "Operario de planta", "edad": 33,
     "localidad": "Santa Lucía, San Juan", "celular": "264 15 078-5520",
     "estudios": "Secundario incompleto (hasta 4° año)",
     "experiencia": "Operario de bodega y peón de carga en distribuidora de bebidas",
     "detalle": ["Carga y descarga, armado de pallets, orden de depósito."],
     "oficio": "Operario general"},
    {"nombre": "Emilce Soledad Videla Ruiz", "titulo": "Operaria de envasado", "edad": 38,
     "localidad": "Chimbas, San Juan", "celular": "264 15 033-6407",
     "estudios": "Secundario completo (Perito Mercantil)",
     "experiencia": "Seis años en línea de fraccionamiento de una bodega de Caucete",
     "detalle": ["Control de llenado, etiquetado y encajonado."],
     "oficio": "Operaria de bodega en línea de envasado"},
    {"nombre": "Tobías Agustín Carrizo Páez", "titulo": "Ayudante de bodega", "edad": 19,
     "localidad": "Rivadavia, San Juan", "celular": "264 15 090-2216",
     "experiencia": "Ayudante de cosecha y de bodega familiar en temporada",
     "detalle": ["Disponibilidad horaria completa durante la vendimia."],
     "oficio": "Operario de bodega"},
    {"nombre": "Marcos Ezequiel Olguín", "titulo": "Técnico electromecánico", "edad": 35,
     "localidad": "Capital, San Juan", "celular": "264 15 027-8843",
     "estudios": "Secundario completo; Técnico Electromecánico (escuela industrial)",
     "experiencia": "Mantenimiento de bombas, compresores y cintas en planta agroindustrial",
     "detalle": ["Tableros eléctricos, motores trifásicos y mantenimiento preventivo."],
     "oficio": "Electricista y mecánico de mantenimiento"},
    {"nombre": "Julián Andrés Ozán", "titulo": "Mecánico industrial", "edad": 46,
     "localidad": "Caucete, San Juan", "celular": "264 15 054-3170",
     "estudios": "Secundario completo",
     "experiencia": "Mecánico de mantenimiento en fábrica de envases durante 12 años",
     "detalle": ["Soldadura eléctrica y MIG, torno y fresa."],
     "oficio": "Mecánico, soldador"},
    {"nombre": "Paola Andrea Fuentes Lima", "titulo": "Administrativa contable", "edad": 31,
     "localidad": "Rawson, San Juan", "celular": "264 15 069-4458",
     "estudios": "Secundario completo; estudiante avanzada de Contador Público",
     "experiencia": "Administrativa contable en estudio de la ciudad (4 años)",
     "detalle": ["Liquidación de proveedores, conciliaciones bancarias."],
     "oficio": "Administración y contabilidad"},
)


def cargar_seleccion(api: Api) -> tuple[int, int]:
    rrhh = {"actor": ACTOR_RRHH}
    busquedas = [api("POST", "seleccion/busquedas", "RRHH", **rrhh, cuerpo=b) for b in BUSQUEDAS]
    archivos = [{"nombre": f"CV_{cv['nombre'].replace(' ', '_')}.pdf",
                 "contenido_base64": b64(pdf_cv(cv))} for cv in CVS]
    incorporados = api("POST", "seleccion/cvs/lote", "RRHH", **rrhh,
                       cuerpo={"archivos": archivos})["incorporados"]
    # RRHH ya revisó y confirmó algunos datos leídos de los primeros CV.
    for cv_id in incorporados[:3]:
        ficha = api("GET", f"seleccion/cvs/{cv_id}?busqueda_id={busquedas[0]['id']}", "RRHH",
                    **rrhh)
        for campo in ficha["campos"][:3]:
            api("PUT", f"seleccion/cvs/{cv_id}/campos/{campo['nombre']}/confirmacion", "RRHH",
                **rrhh, cuerpo={"valor": campo["valor"]})
    return len(busquedas), len(incorporados)


ADJUNTOS_LEGAJO = (
    ("Constancia de capacitación en autoelevadores", {"OP-AUT", "OP-PAN"},
     ["Aprobó el curso teórico-práctico de manejo seguro de autoelevadores.",
      "Carga horaria: 4 horas. Evaluación práctica: aprobada."]),
    ("Apto médico preocupacional", None,
     ["Resultado del examen preocupacional: APTO para el puesto asignado.",
      "Examen clínico, audiometría y espirometría sin observaciones."]),
    ("Constancia de entrega de reglamento interno", None,
     ["Recibió copia del reglamento interno y de las normas de seguridad",
      "e higiene del establecimiento, y se notificó de su contenido."]),
)


def cargar_adjuntos_legajo(api: Api, personas: list[dict], hoy: date) -> int:
    cargados = 0
    for indice, persona in enumerate(personas):
        for titulo, puestos, lineas in ADJUNTOS_LEGAJO:
            if puestos is not None and persona["puesto_codigo"] not in puestos:
                continue
            if puestos is None and indice % 3:
                continue
            fecha = dia_habil(hoy - timedelta(days=AZAR.randint(5, DIAS_HISTORIA)))
            api("POST", "legajo/adjuntos", "RRHH", empresa=persona["empresa"], actor=ACTOR_RRHH,
                cuerpo={"legajo": persona["legajo"],
                        "nombre": f"{titulo.replace(' ', '_')}_{persona['legajo']}.pdf",
                        "contenido_base64": b64(pdf_constancia_legajo(titulo, persona, lineas,
                                                                     fecha))})
            cargados += 1
    return cargados


def cargar_turnos(api: Api, personas: list[dict], hoy: date) -> int:
    """Sólo días por venir: los días cerrados no admiten cronograma nuevo."""
    bodega = [p for p in personas if p["sector"] == "Bodega"]
    lunes = hoy + timedelta(days=7 - hoy.weekday())
    turnos = ((time(6), time(14)), (time(14), time(22)))
    cargados = 0
    for semana in range(2):
        asignaciones = []
        for orden, persona in enumerate(bodega):
            desde, hasta = turnos[(orden + semana) % 2]
            asignaciones += [{"legajo": persona["legajo"],
                              "fecha": (lunes + timedelta(days=7 * semana + d)).isoformat(),
                              "desde": desde.isoformat("minutes"),
                              "hasta": hasta.isoformat("minutes")} for d in range(5)]
        if asignaciones:
            cargados += len(api("POST", "turnos/cronogramas/semana", "SUPERADMIN",
                                actor=ACTOR_SUPERVISOR,
                                cuerpo={"sector": "Bodega", "asignaciones": asignaciones}))
    return cargados


# --------------------------------------------------------------------------
# Resumen con los mismos GET que usa la pantalla
# --------------------------------------------------------------------------


def resumen(api: Api, hoy: date) -> dict[str, object]:
    inicio = date(hoy.year, 1, 1).isoformat()
    desde = (hoy - timedelta(days=DIAS_HISTORIA + 7)).isoformat()
    sa = {"actor": ACTOR_RRHH}
    personas = api("GET", "legajo/personas", "SUPERADMIN", **sa)
    entregas = api("GET", f"rrhh-epp/entregas?desde={inicio}&hasta={hoy}", "SUPERADMIN", **sa)
    stock = api("GET", "rrhh-epp/stock", "SUPERADMIN", **sa)
    temas = api("GET", "capacitaciones/temas", "SUPERADMIN", **sa)
    certificados = api("GET", "salud/certificados", "MEDICO", actor=ACTOR_MEDICO)
    return {
        "legajos": len(personas),
        "adjuntos_legajo": sum(
            len(api("GET", f"legajo/personas/{p['legajo']}/adjuntos", "SUPERADMIN", **sa))
            for p in personas),
        "entregas_epp": len(entregas),
        "ultimas_entregas": [f"{e['fecha']} · {e['persona']} · {e['motivo']}"
                             for e in entregas[-3:]],
        "items_bajo_minimo": sum(s["disponible"] < s["minimo"] for s in stock),
        "avisos_compras": len(api("GET", "rrhh-epp/avisos-compras", "SUPERADMIN", **sa)),
        "metricas_analitica": len(api("GET", f"epp-analitica/tablero?desde={desde}&hasta={hoy}",
                                      "SUPERADMIN", **sa)["metricas"]),
        "temas_capacitacion": len(temas),
        "dictados": sum(len(t["dictados"]) for t in temas),
        "asistencias": sum(
            len(api("GET", f"capacitaciones/dictados/{d['id']}/asistencias", "SUPERADMIN", **sa))
            for t in temas for d in t["dictados"]),
        "certificados_medicos": len(certificados),
        "diagnosticos_en_reporte": len(
            api("GET", "salud/reportes", "MEDICO", actor=ACTOR_MEDICO)["por_diagnostico"]),
        "bitacora_salud": len(api("GET", "salud/bitacora", "MEDICO", actor=ACTOR_MEDICO)),
        "busquedas": len(api("GET", "seleccion/busquedas", "SUPERADMIN", **sa)),
        "cvs": len(api("GET", "seleccion/cvs", "SUPERADMIN", **sa)),
        "cronogramas_bodega": len(api("GET", "turnos/cronogramas?sector=Bodega", "SUPERADMIN",
                                      **sa)),
    }


def main() -> None:
    marca = ruta_marca()
    if marca.exists():
        print(f"La demostración ya estaba cargada ({marca}). No se hizo nada.")
        return
    verificar_entorno()

    from fastapi.testclient import TestClient

    from suite_juviar.main import app

    hoy = datetime.now(ZONA).date()
    with TestClient(app) as http:
        api = Api(http)
        if api("GET", "capacitaciones/temas", "SUPERADMIN", actor=ACTOR_RRHH):
            print("La base ya tiene datos de Gestión: no se carga la demostración encima.")
            marca.write_text(json.dumps({"omitida": datetime.now(UTC).isoformat()}) + "\n")
            return
        personas = leer_personas(api)
        cargado = {
            "entregas_epp": cargar_epp(api, personas, hoy),
            "capacitaciones": cargar_capacitaciones(api, personas, hoy),
            "certificados": cargar_salud(api, personas, hoy),
            "seleccion": cargar_seleccion(api),
            "adjuntos_legajo": cargar_adjuntos_legajo(api, personas, hoy),
            "cronogramas": cargar_turnos(api, personas, hoy),
        }
        estado = resumen(api, hoy)
    marca.write_text(json.dumps(
        {"cargada_en": datetime.now(UTC).isoformat(), "cargado": cargado, "resumen": estado},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Demostración cargada:")
    for clave, valor in estado.items():
        print(f"  {clave}: {valor}")


if __name__ == "__main__":
    main()
