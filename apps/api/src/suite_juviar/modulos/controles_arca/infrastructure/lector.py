"""Lectura del texto de la foto de una factura que no trae QR.

Por defecto se lee con tesseract dentro del servidor (la foto no sale de la empresa).
Sólo si hay clave de DeepSeek (``SJ_SALUD_IA_API_KEY``) **y** alguien lo autorizó
expresamente con ``SJ_CONTROLES_ARCA_IA_EXTERNA_AUTORIZADA=si`` la foto se manda a DeepSeek.
Sin las dos cosas, sólo OCR local: si falta la autorización no se manda nada afuera.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

from suite_juviar.plataforma.ocr import leer_texto_imagen

_EXTENSIONES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_SI = {"1", "true", "si", "sí"}


def ia_externa_autorizada() -> bool:
    return (bool(os.getenv("SJ_SALUD_IA_API_KEY", "").strip())
            and os.getenv("SJ_CONTROLES_ARCA_IA_EXTERNA_AUTORIZADA", "").strip().lower() in _SI)


class LectorFacturasLocal:
    def __init__(self, ia_externa: bool | None = None) -> None:
        self.ia_externa = ia_externa_autorizada() if ia_externa is None else ia_externa

    def leer(self, contenido: bytes, tipo: str) -> tuple[str, str]:
        if self.ia_externa:
            return _leer_con_deepseek(contenido, tipo, os.getenv("SJ_SALUD_IA_API_KEY", "").strip()), "deepseek"
        return leer_texto_imagen(contenido, _EXTENSIONES.get(tipo, ".jpg")), "ocr"


def _leer_con_deepseek(contenido: bytes, tipo: str, clave: str) -> str:
    """Manda la foto de la factura a DeepSeek: la imagen SALE de la empresa."""
    instrucciones = """Transcribí el texto de esta factura argentina tal como se ve, línea por línea.
No inventes ni completes datos ilegibles. Respondé sólo el texto, sin comentarios."""
    cuerpo = {
        "model": os.getenv("SJ_SALUD_IA_MODELO", "deepseek-flash"),
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": instrucciones},
            {"type": "image_url", "image_url": {
                "url": f"data:{tipo};base64,{base64.b64encode(contenido).decode()}", "detail": "original"}},
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
        return str(salida["choices"][0]["message"]["content"])
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("La IA no pudo leer la factura. Cargá los datos a mano mirando el papel.") from exc
