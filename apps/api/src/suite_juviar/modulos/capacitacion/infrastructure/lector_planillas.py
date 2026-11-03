"""Lectura de planillas de asistencia escaneadas.

Con `SJ_CAPACITACION_IA_API_KEY` las fotos se envían a DeepSeek para que diga quién firmó
(la imagen SALE de la empresa). Sin clave no se lee nada: las filas salen de la planilla
impresa y quien revisa marca presente o ausente mirando la imagen.
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from ..domain.modelos import FilaPlanilla

_IMAGENES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def usaria_ia_externa(nombre: str) -> bool:
    return bool(os.getenv("SJ_CAPACITACION_IA_API_KEY", "").strip()) and Path(nombre).suffix.lower() in _IMAGENES


class LectorPlanillasIA:
    def leer(self, nombre: str, contenido: bytes,
             esperados: list[FilaPlanilla]) -> tuple[list[FilaPlanilla], str, str]:
        if usaria_ia_externa(nombre):
            return _leer_con_deepseek(nombre, contenido, esperados,
                                      os.getenv("SJ_CAPACITACION_IA_API_KEY", "").strip())
        filas = [FilaPlanilla(f.legajo, f.nombre_completo, None) for f in esperados]
        if not filas:
            return [], "manual", "Sin lectura automática. Cargá las filas mirando la imagen."
        return filas, "manual", ("Sin lectura automática: marcá presente o ausente en cada fila "
                                 "mirando la imagen, y agregá a quien se anotó a mano.")


def _leer_con_deepseek(nombre: str, contenido: bytes, esperados: list[FilaPlanilla],
                       clave: str) -> tuple[list[FilaPlanilla], str, str]:
    mime = _IMAGENES[Path(nombre).suffix.lower()]
    lista = "\n".join(f"- {f.legajo}: {f.nombre_completo}" for f in esperados) or "(ninguna)"
    instrucciones = f"""Esta es una planilla de asistencia a una capacitación, firmada a mano.
Personas impresas en la planilla:
{lista}
Puede haber filas agregadas a mano. No inventes datos ilegibles.
Respondé solamente JSON válido: {{"filas": [{{"legajo": "...", "nombre_completo": "...",
"firmo": true | false | null}}]}}. firmo es true si la fila tiene firma o marca de presente,
false si está vacía o dice ausente, y null si no se puede saber."""
    cuerpo = {
        "model": os.getenv("SJ_CAPACITACION_IA_MODELO", "deepseek-flash"),
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": instrucciones},
            {"type": "image_url", "image_url": {
                "url": f"data:{mime};base64,{base64.b64encode(contenido).decode()}", "detail": "original"}},
        ]}],
        "thinking": {"type": "disabled"},
        "temperature": 0,
        "max_tokens": 2000,
    }
    solicitud = urllib.request.Request(
        "https://api.deepseek.com/chat/completions", data=json.dumps(cuerpo).encode(),
        headers={"Authorization": f"Bearer {clave}", "Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(solicitud, timeout=60) as respuesta:
            salida = json.loads(respuesta.read())
        texto = salida["choices"][0]["message"]["content"].strip()
        datos = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", texto, flags=re.IGNORECASE))
        leidas = datos["filas"]
    except (urllib.error.URLError, TimeoutError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("La IA no pudo leer la planilla. Revisá la conexión o la clave y volvé a intentar.") from exc
    impresos = {f.legajo: f for f in esperados}
    filas: dict[str, FilaPlanilla] = {}
    for fila in leidas if isinstance(leidas, list) else []:
        if not isinstance(fila, dict):
            continue
        legajo = str(fila.get("legajo") or "").strip()
        if not legajo or legajo in filas:
            continue
        firmo = fila.get("firmo")
        if legajo in impresos:
            filas[legajo] = FilaPlanilla(legajo, impresos[legajo].nombre_completo,
                                         firmo if isinstance(firmo, bool) else None)
        else:
            # Lo que la IA dice que se agregó a mano llega sin marcar: lo decide quien revisa.
            filas[legajo] = FilaPlanilla(legajo, str(fila.get("nombre_completo") or "").strip(), None)
    # Quien estaba impreso y la IA no devolvió queda para que lo decida quien revisa.
    for legajo, fila in impresos.items():
        filas.setdefault(legajo, FilaPlanilla(legajo, fila.nombre_completo, None))
    return list(filas.values()), "deepseek", "La IA leyó la planilla. Revisá cada fila contra la imagen antes de aprobar."
