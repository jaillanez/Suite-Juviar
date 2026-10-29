"""Conversaciones que la gente tuvo con el bot de WhatsApp, en sólo lectura.

Lee la cola del bot (consulta.bot_entrada): cada mensaje recibido con la respuesta que el
bot mandó. El nombre sale de los contactos de productores (consulta.telefono_productor y
el padrón de la fila) o del personal cargado (consulta.telefono_personal). Nada se escribe desde acá.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query

from suite_juviar.plataforma.identidad.api.dependencias import exigir_permiso
from suite_juviar.plataforma.identidad.domain.sesion import Sesion

from .tablero_fila import _leer

router = APIRouter(prefix="/conversaciones-bot", tags=["bot"])
Autorizado = Annotated[Sesion, Depends(exigir_permiso("bot.conversaciones.leer"))]

LISTADO = """
WITH ultimas AS (
    SELECT telefono, count(*) AS mensajes, max(recibido_en) AS ultimo_en
      FROM consulta.bot_entrada
     WHERE recibido_en >= now() - make_interval(days => %(dias)s)
     GROUP BY telefono
)
SELECT u.telefono, u.mensajes, u.ultimo_en,
       (SELECT coalesce(e.texto, '[' || e.tipo || ']') FROM consulta.bot_entrada e
         WHERE e.telefono = u.telefono ORDER BY e.recibido_en DESC, e.id DESC LIMIT 1) AS ultimo_texto,
       coalesce(
         (SELECT string_agg(DISTINCT p.razonsocial, ' · ')
            FROM consulta.telefono_productor t JOIN fila.productor p ON p.clientecuit = t.clientecuit
           WHERE t.telefono = u.telefono AND t.activo),
         -- El nombre del personal sólo lo ve quien administra el personal del bot.
         (SELECT CASE WHEN %(ve_personal)s THEN e.nombre ELSE 'Personal de la empresa' END
            FROM consulta.telefono_personal e
           WHERE e.telefono = u.telefono AND e.activo)) AS nombre,
       CASE WHEN EXISTS (SELECT 1 FROM consulta.telefono_personal e
                          WHERE e.telefono = u.telefono AND e.activo)
            THEN (SELECT CASE WHEN %(ve_personal)s THEN e.tipo ELSE 'personal' END
                    FROM consulta.telefono_personal e WHERE e.telefono = u.telefono)
            WHEN EXISTS (SELECT 1 FROM consulta.telefono_productor t
                          WHERE t.telefono = u.telefono AND t.activo)
            THEN 'productor' END AS quien
  FROM ultimas u
 ORDER BY u.ultimo_en DESC
 LIMIT 200
"""

MENSAJES = """
SELECT id, tipo, texto, recibido_en, estado, respuesta, procesado_en
  FROM consulta.bot_entrada
 WHERE telefono = %(telefono)s
 ORDER BY recibido_en DESC, id DESC
 LIMIT 300
"""

AVISOS = {"ignorado": "El bot no respondió (tope de mensajes por hora).",
          "error": "El bot no pudo responder este mensaje."}


def armar_chat(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cada mensaje recibido y su respuesta, en orden de llegada."""
    chat: list[dict[str, Any]] = []
    for fila in sorted(filas, key=lambda f: (f["recibido_en"], f["id"])):
        chat.append({"id": f"e{fila['id']}", "de": "persona",
                     "texto": fila["texto"] or f"[{fila['tipo']}]", "momento": fila["recibido_en"]})
        momento: datetime = fila["procesado_en"] or fila["recibido_en"]
        if fila["respuesta"]:
            chat.append({"id": f"r{fila['id']}", "de": "bot", "texto": fila["respuesta"], "momento": momento})
        elif fila["estado"] in AVISOS:
            chat.append({"id": f"a{fila['id']}", "de": "aviso", "texto": AVISOS[fila["estado"]], "momento": momento})
    return chat


@router.get("")
def conversaciones(sesion: Autorizado, dias: int = Query(30, ge=1, le=365)):
    return _leer(LISTADO, {"dias": dias, "ve_personal": sesion.puede("bot.personal.gestionar")})


@router.get("/{telefono}")
def conversacion(_: Autorizado, telefono: str = Path(pattern=r"^\d{8,20}$")):
    return armar_chat(_leer(MENSAJES, {"telefono": telefono}))
