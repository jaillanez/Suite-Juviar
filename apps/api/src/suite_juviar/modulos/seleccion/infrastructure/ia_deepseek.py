"""Lectura de currículums y búsqueda de candidatos con DeepSeek.

La IA sólo propone: arma una ficha de cada CV y ordena candidatos para un pedido escrito
por RRHH. Nada se decide solo; la persona revisa el original antes de avanzar.
El CV SALE de la empresa hacia DeepSeek: en producción requiere autorización expresa.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

IMAGENES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
ENCAJES = ("ALTO", "MEDIO", "BAJO")


def clave() -> str:
    return (os.getenv("SJ_IA_DEEPSEEK_API_KEY") or os.getenv("SJ_SALUD_IA_API_KEY") or "").strip()


def disponible() -> bool:
    return bool(clave())


def _llamar(contenido: list[dict[str, object]], max_tokens: int) -> dict[str, object]:
    cuerpo = {
        "model": os.getenv("SJ_IA_DEEPSEEK_MODELO") or os.getenv("SJ_SALUD_IA_MODELO") or "deepseek-flash",
        "messages": [{"role": "user", "content": contenido}],
        "thinking": {"type": "disabled"},
        "reasoning_effort": "none",
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    solicitud = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(cuerpo).encode(),
        headers={"Authorization": f"Bearer {clave()}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(solicitud, timeout=120) as respuesta:
            salida = json.loads(respuesta.read())
        texto = salida["choices"][0]["message"]["content"].strip()
        texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto, flags=re.IGNORECASE)
        datos = json.loads(texto)
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("La IA no respondió bien. Revisá la conexión o la clave y volvé a intentar.") from exc
    if not isinstance(datos, dict):
        raise RuntimeError("La IA devolvió una respuesta inesperada.")  # noqa: TRY004 - error de servicio, no de tipos
    return datos


INSTRUCCIONES_LECTURA = """Leé este currículum (en español) y armá una ficha. No inventes nada: si un dato
no está, usá null o una lista vacía. Respondé solamente JSON válido con estas claves:
nombre_completo, localidad, provincia, edad, estudios (lista de textos), experiencia (lista de
objetos con puesto, empresa, periodo), oficios (lista: p. ej. tractorista, soldador, administrativo,
jornalero, capataz), idiomas (lista), licencia_conducir (texto o null), habilidades (lista),
disponibilidad (texto o null), resumen (2 o 3 líneas para RRHH).
Como máximo 10 experiencias (las más recientes) y 15 habilidades."""


def _paginas_como_imagen(contenido: bytes, maximo: int = 3) -> list[str]:
    """PDF escaneado (sin texto): las primeras páginas como PNG en base64."""
    import pypdfium2

    try:
        documento = pypdfium2.PdfDocument(contenido)
    except pypdfium2.PdfiumError:
        return []
    paginas = []
    for indice in range(min(len(documento), maximo)):
        imagen = documento[indice].render(scale=1.6).to_pil()
        salida = io.BytesIO()
        imagen.save(salida, format="PNG")
        paginas.append(base64.b64encode(salida.getvalue()).decode())
    return paginas


def leer_cv(nombre: str, contenido: bytes, texto: str) -> dict[str, object]:
    extension = Path(nombre).suffix.lower()
    if texto.strip():
        partes: list[dict[str, object]] = [
            {"type": "text", "text": f"{INSTRUCCIONES_LECTURA}\n\nCURRÍCULUM:\n{texto[:20000]}"}
        ]
    elif extension in IMAGENES:
        datos = base64.b64encode(contenido).decode()
        partes = [
            {"type": "text", "text": INSTRUCCIONES_LECTURA},
            {"type": "image_url", "image_url": {"url": f"data:{IMAGENES[extension]};base64,{datos}",
                                                "detail": "original"}},
        ]
    elif extension == ".pdf" and (paginas := _paginas_como_imagen(contenido)):
        partes = [{"type": "text", "text": INSTRUCCIONES_LECTURA}] + [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{p}", "detail": "original"}}
            for p in paginas
        ]
    else:
        raise RuntimeError("No se pudo leer este archivo: no es PDF ni imagen, o está dañado.")
    ficha = _llamar(partes, 4000)
    ficha.pop("texto", None)
    return ficha


def buscar_candidatos(pedido: str, fichas: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    """Ordena las fichas según el pedido de RRHH. Devuelve encaje, motivos y lo que falta."""
    if not fichas:
        return []
    listado = json.dumps(
        [{"id": cv_id, **{k: v for k, v in ficha.items() if k != "resumen"}, "resumen": ficha.get("resumen")}
         for cv_id, ficha in fichas.items()],
        ensure_ascii=False,
    )
    instrucciones = f"""Sos asistente de Recursos Humanos de una bodega de San Juan, Argentina.
El pedido de RRHH es: «{pedido}».
Evaluá a TODOS los candidatos de la lista sólo con los datos de su ficha; no supongas lo que
no está escrito. Respondé solamente JSON válido: {{"candidatos": [{{"id": ..., "encaje": "ALTO" |
"MEDIO" | "BAJO", "motivos": [frases cortas con lo que cumple, citando el dato], "faltan":
[frases cortas con lo que no cumple o no dice]}}]}}, ordenado de mejor a peor encaje.

CANDIDATOS:
{listado}"""
    datos = _llamar([{"type": "text", "text": instrucciones}], 4000)
    resultado = []
    for candidato in datos.get("candidatos") or []:
        if not isinstance(candidato, dict) or candidato.get("id") not in fichas:
            continue
        encaje = str(candidato.get("encaje") or "").upper()
        resultado.append({
            "id": candidato["id"],
            "encaje": encaje if encaje in ENCAJES else "BAJO",
            "motivos": [str(m) for m in candidato.get("motivos") or []][:8],
            "faltan": [str(m) for m in candidato.get("faltan") or []][:8],
        })
    orden = {e: i for i, e in enumerate(ENCAJES)}
    return sorted(resultado, key=lambda c: orden[c["encaje"]])
