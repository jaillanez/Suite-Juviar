"""Botones y listas de WhatsApp (mensajes interactivos de Cloud API), sólo por Meta directo.

Las reglas son las de Meta:
  * hasta 3 opciones: botones de respuesta, con título de hasta 20 caracteres;
  * de 4 a 10: una lista, con filas de hasta 24 caracteres y descripción de hasta 72;
  * más de 10: la lista muestra 9 y una fila «Ver más…» que pide las siguientes.
El texto del mensaje va como cuerpo (hasta 1024 caracteres).

Cada opción viaja con un id estable, ``op:<opción completa>``: cuando la persona toca un botón,
el webhook (meta.py) entrega ese id y el diálogo lo reconoce aunque el título haya salido
recortado o la lista haya cambiado de orden. «Ver más…» viaja como ``pag:<desde>``.
En el simulador y por Chattigo no se usa: sale el texto con las opciones numeradas.
"""
from __future__ import annotations

MAX_CUERPO = 1024
MAX_BOTONES = 3
MAX_FILAS = 10
TITULO_BOTON, TITULO_FILA, DESCRIPCION_FILA = 20, 24, 72
MAX_ID = 200
TEXTO_LISTA = "Ver opciones"


def recortar(texto: str, maximo: int) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= maximo else texto[: maximo - 1].rstrip() + "…"


def id_opcion(opcion: str) -> str:
    return f"op:{opcion}"[:MAX_ID]


def _botones(opciones: list[str]) -> dict | None:
    titulos = [recortar(o, TITULO_BOTON) for o in opciones]
    if len(set(titulos)) != len(titulos):  # Meta no acepta dos botones con el mismo título
        return None
    return {
        "type": "button",
        "action": {"buttons": [
            {"type": "reply", "reply": {"id": id_opcion(o), "title": t}}
            for o, t in zip(opciones, titulos, strict=True)
        ]},
    }


def _lista(opciones: list[str], desde: int) -> dict:
    desde = desde if 0 <= desde < len(opciones) else 0
    restantes = opciones[desde:]
    siguiente = None
    if len(restantes) > MAX_FILAS:
        restantes, siguiente = restantes[: MAX_FILAS - 1], desde + MAX_FILAS - 1
    filas = []
    for opcion in restantes:
        fila = {"id": id_opcion(opcion), "title": recortar(opcion, TITULO_FILA)}
        if len(opcion) > TITULO_FILA:
            fila["description"] = recortar(opcion, DESCRIPCION_FILA)
        filas.append(fila)
    if siguiente is not None:
        quedan = len(opciones) - siguiente
        filas.append({"id": f"pag:{siguiente}", "title": "Ver más…",
                      "description": f"{quedan} opción más" if quedan == 1 else f"{quedan} opciones más"})
    return {"type": "list", "action": {"button": TEXTO_LISTA, "sections": [{"rows": filas}]}}


def cuerpo_opciones(telefono: str, texto: str, opciones: list[str], desde: int = 0) -> dict:
    """Mensaje interactivo con el texto como cuerpo (recortado a 1024)."""
    if not opciones:
        raise ValueError("un mensaje con botones necesita opciones")
    interactivo = None
    if len(opciones) <= MAX_BOTONES and desde == 0:
        interactivo = _botones(opciones)
    interactivo = interactivo or _lista(opciones, desde)
    interactivo["body"] = {"text": texto if len(texto) <= MAX_CUERPO else texto[: MAX_CUERPO - 1] + "…"}
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefono,
        "type": "interactive",
        "interactive": interactivo,
    }


def partir_cuerpo(texto: str) -> tuple[str | None, str]:
    """(texto que va antes, cuerpo). Si el texto no entra como cuerpo, lo largo sale antes como
    mensaje de texto y los botones llevan el último párrafo (la pregunta)."""
    if len(texto) <= MAX_CUERPO:
        return None, texto
    antes, _, ultimo = texto.rpartition("\n\n")
    if antes and len(ultimo) <= MAX_CUERPO:
        return antes, ultimo
    return texto, "¿Qué querés hacer?"
