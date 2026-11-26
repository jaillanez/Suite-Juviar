"""Los datos de cada CV que ve RRHH: lo que leyó la IA y, si la IA no lo encontró, lo que leyeron las reglas.

Nada de esto está confirmado: cada dato dice de dónde salió y sigue «sin confirmar» hasta que RRHH
lo compara con el original y lo confirma. Lo confirmado por RRHH manda sobre cualquier lectura.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..domain.modelos import CampoExtraido, ConfirmacionCampo, ExtraccionCV
from .extraccion import CAMPOS_REQUERIDOS

ZONA = ZoneInfo("America/Argentina/San_Juan")
VERSION_FICHA = 2  # la ficha de la IA trae fecha de nacimiento, nivel de estudios y contacto
DE_LA_IA = "IA"
DE_LAS_REGLAS = "LECTURA_AUTOMATICA"
DE_RRHH = "RRHH"
FRAGMENTO_IA = "Leído por la IA en el archivo original"

# Estado de la lectura con IA de un CV.
LEIDO = "LEIDO"
EN_COLA = "EN_COLA"
LEYENDO = "LEYENDO"
ERROR = "ERROR"
SIN_LEER = "SIN_LEER"
NO_DISPONIBLE = "NO_DISPONIBLE"

# Por qué falta un dato obligatorio.
NO_LO_ENCONTRO = "NO_LO_ENCONTRO"  # la IA leyó el CV completo y no lo encontró
NO_SE_PUDO_LEER = "NO_SE_PUDO_LEER"  # sin IA (o falló) y las reglas no lo encontraron
TODAVIA_LEYENDO = "LEYENDO"  # la IA lo está leyendo


def hoy() -> date:
    return datetime.now(ZONA).date()


def edad_a(nacimiento: date, dia: date) -> int:
    return dia.year - nacimiento.year - ((dia.month, dia.day) < (nacimiento.month, nacimiento.day))


def _texto(valor: object) -> str:
    if valor is None or isinstance(valor, bool):
        return ""
    if isinstance(valor, (list, tuple)):
        return " · ".join(t for t in (_texto(v) for v in valor) if t)
    if isinstance(valor, dict):
        return " · ".join(t for t in (_texto(v) for v in valor.values()) if t)
    return str(valor).strip()


def _fecha(texto: str) -> date | None:
    hallada = re.fullmatch(r"\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\s*", texto) or None
    if hallada:
        try:
            return date(int(hallada.group(3)), int(hallada.group(2)), int(hallada.group(1)))
        except ValueError:
            return None
    try:
        return date.fromisoformat(texto.strip())
    except ValueError:
        return None


def _edad_de_ficha(ficha: Mapping[str, object], dia: date) -> str:
    edad = re.search(r"\d{1,2}", _texto(ficha.get("edad")))
    texto_fecha = _texto(ficha.get("fecha_nacimiento"))
    nacimiento = _fecha(texto_fecha) if texto_fecha else None
    if nacimiento and 14 <= edad_a(nacimiento, dia) <= 99:
        calculada = edad_a(nacimiento, dia)
        fecha = nacimiento.strftime("%d/%m/%Y")
        if edad and abs(int(edad.group()) - calculada) > 1:
            return f"{calculada} años hoy (nació el {fecha}; el CV dice {edad.group()})"
        return f"{calculada} años (nació el {fecha})"
    if edad and 14 <= int(edad.group()) <= 99:
        return f"{edad.group()} años"
    return f"Nació el {texto_fecha}" if texto_fecha else ""


def _experiencia(ficha: Mapping[str, object]) -> str:
    items = []
    for item in ficha.get("experiencia") or []:
        if isinstance(item, dict):
            puesto, empresa, periodo = (_texto(item.get(k)) for k in ("puesto", "empresa", "periodo"))
            texto = " en ".join(x for x in (puesto, empresa) if x)
            items.append(f"{texto} ({periodo})" if texto and periodo else texto or periodo)
        else:
            items.append(_texto(item))
    return "; ".join(i for i in items if i)


def valores_de_ficha(ficha: Mapping[str, object] | None, dia: date | None = None) -> dict[str, str]:
    """Los seis datos de RRHH, tal como los dejó la IA en la ficha (sólo los que trae)."""
    if not ficha:
        return {}
    dia = dia or hoy()
    localidad, provincia = _texto(ficha.get("localidad")), _texto(ficha.get("provincia"))
    if provincia and provincia.casefold() not in localidad.casefold():
        localidad = f"{localidad}, {provincia}" if localidad else provincia
    valores = {
        "edad_o_fecha_nacimiento": _edad_de_ficha(ficha, dia),
        "nivel_estudios": _texto(ficha.get("nivel_estudios")) or _texto(ficha.get("estudios")),
        "experiencia": _experiencia(ficha),
        "oficio": _texto(ficha.get("oficios")),
        "localidad": localidad,
        "contacto": " · ".join(x for x in (_texto(ficha.get("telefono")), _texto(ficha.get("email"))) if x),
    }
    return {nombre: valor[:300] for nombre, valor in valores.items() if valor}


def combinar(extraccion: ExtraccionCV | None, ficha: Mapping[str, object] | None,
             confirmaciones: Iterable[ConfirmacionCampo] = (), dia: date | None = None) -> list[dict[str, object]]:
    """Un dato por campo: lo confirmado por RRHH, si no lo de la IA, si no lo de las reglas."""
    reglas = {campo.nombre: campo for campo in extraccion.campos} if extraccion else {}
    ia = valores_de_ficha(ficha, dia)
    confirmados = {c.campo: c for c in confirmaciones}
    datos = []
    for nombre in CAMPOS_REQUERIDOS:
        regla = reglas.get(nombre)
        if nombre in confirmados:
            dato = {"valor": confirmados[nombre].valor, "origen": DE_RRHH,
                    "fragmento_fuente": regla.fragmento_fuente if regla else FRAGMENTO_IA}
        elif nombre in ia:
            dato = {"valor": ia[nombre], "origen": DE_LA_IA, "fragmento_fuente": FRAGMENTO_IA}
            if regla and regla.valor.casefold() != ia[nombre].casefold():
                dato["otra_lectura"] = regla.valor  # lo que leyeron las reglas, para comparar
        elif regla:
            dato = {"valor": regla.valor, "origen": DE_LAS_REGLAS, "fragmento_fuente": regla.fragmento_fuente}
        else:
            continue
        datos.append({"nombre": nombre, "verificado": False, **dato})
    return datos


def extraccion_combinada(extraccion: ExtraccionCV | None, datos: list[dict[str, object]],
                         id_original: str) -> ExtraccionCV:
    """La extracción con los datos combinados, para evaluar las búsquedas con todo lo leído."""
    campos = tuple(CampoExtraido(str(d["nombre"]), str(d["valor"]), str(d["fragmento_fuente"])) for d in datos)
    presentes = {campo.nombre for campo in campos}
    pendientes = tuple(c for c in CAMPOS_REQUERIDOS if c not in presentes)
    if extraccion is None:
        return ExtraccionCV(id_original, campos, pendientes, datetime.now(ZONA))
    return replace(extraccion, campos=campos, campos_pendientes=pendientes)


def motivo_faltantes(estado_ia: str) -> str:
    """Por qué faltan los datos: nunca se dice que el CV no los trae si no se pudo leer."""
    if estado_ia in {EN_COLA, LEYENDO}:
        return TODAVIA_LEYENDO
    return NO_LO_ENCONTRO if estado_ia == LEIDO else NO_SE_PUDO_LEER
