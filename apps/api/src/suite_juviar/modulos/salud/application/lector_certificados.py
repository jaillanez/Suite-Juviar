from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path

from suite_juviar.plataforma.ocr import leer_texto_imagen

IMAGENES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
PAGINAS_PDF_IA = 2


def _clave() -> str:
    """La misma clave de DeepSeek que usa la lectura de CV; la de Salud queda como alternativa."""
    return (os.getenv("SJ_SALUD_IA_API_KEY") or os.getenv("SJ_IA_DEEPSEEK_API_KEY") or "").strip()


def usaria_ia_externa(nombre: str) -> bool:
    """Indica si este archivo se enviaría a DeepSeek (fuera de la empresa): fotos y PDF."""
    return bool(_clave()) and nombre.lower().endswith((*IMAGENES, ".pdf"))


def _texto_pdf(contenido: bytes) -> str:
    try:
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(contenido)).pages)
    except Exception:  # noqa: BLE001 - PDF dañado o sin capa de texto
        return ""


def _imagenes_para_ia(nombre: str, contenido: bytes) -> list[tuple[str, bytes]]:
    """(tipo, bytes) de lo que se le muestra a la IA: la foto, o las primeras hojas del PDF."""
    extension = Path(nombre).suffix.lower()
    if extension in IMAGENES:
        return [(IMAGENES[extension], contenido)]
    from suite_juviar.modulos.seleccion.infrastructure.extraccion_pdf import paginas_png
    return [("image/png", pagina) for pagina in paginas_png(contenido, PAGINAS_PDF_IA, 2.0)]


def analizar_certificado(
    nombre: str, contenido: bytes, *, permitir_ia_externa: bool = True,
) -> dict[str, object]:
    if permitir_ia_externa and usaria_ia_externa(nombre):
        imagenes = _imagenes_para_ia(nombre, contenido)
        if imagenes:
            return _leer_con_deepseek(imagenes, _clave(), _texto_pdf(contenido) if nombre.lower().endswith(".pdf") else "")
    texto = ""
    if nombre.lower().endswith(".pdf"):
        texto = _texto_pdf(contenido)
    elif nombre.lower().endswith((".txt", ".csv")):
        texto = contenido.decode("utf-8", errors="ignore")
    elif nombre.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff")):
        texto = _leer_imagen(contenido, Path(nombre).suffix)

    limpio = " ".join(texto.split())
    dias = None
    coincidencia = re.search(r"\b(\d{1,3})\s*d[ií]as?\b", limpio, re.IGNORECASE)
    if coincidencia:
        dias = int(coincidencia.group(1))

    normalizado = limpio.casefold()
    if any(x in normalizado for x in ("in itinere", "trayecto al trabajo", "camino al trabajo")):
        tipo = "IN_ITINERE"
    elif any(x in normalizado for x in ("accidente laboral", "accidente de trabajo", "art ")):
        tipo = "ACCIDENTE_LABORAL"
    elif "accidente" in normalizado:
        tipo = "ACCIDENTE_A_REVISAR"
    else:
        tipo = "NO_INFORMADO"

    return {
        "resumen": limpio[:500],
        "dias_detectados": dias,
        "tipo_accidente": tipo,
        "texto_detectado": bool(limpio),
        "requiere_revision": True,
        "mensaje": (
            "Se leyó el texto del documento. Revisá los datos antes de guardar."
            if limpio else
            "No se pudo reconocer el texto del archivo. Completá los datos manualmente."
        ),
    }


def _leer_con_deepseek(imagenes: list[tuple[str, bytes]], clave: str, texto_pdf: str = "") -> dict[str, object]:
    """Envía la imagen del certificado a DeepSeek: el dato de salud SALE de la empresa."""
    instrucciones = """Leé este certificado médico (manuscrito o impreso) en español. No inventes datos ilegibles.
Respondé solamente JSON válido con estas claves: transcripcion, resumen, paciente_nombre,
paciente_dni, diagnostico_texto, diagnostico_codigo, fecha_desde, fecha_hasta,
fecha_reintegro, dias_detectados, tipo_accidente, profesional y campos_a_revisar.
Usá null cuando el documento no indique un dato. Fechas en AAAA-MM-DD. tipo_accidente debe ser
NO_INFORMADO, NO_ES_ACCIDENTE, ACCIDENTE_LABORAL, IN_ITINERE o ACCIDENTE_A_REVISAR.
El resumen debe ser breve y útil para novedades de liquidación de sueldos."""
    contenido_ia: list[dict[str, object]] = [{"type": "text", "text": instrucciones}]
    if texto_pdf.strip():
        contenido_ia.append({"type": "text", "text": "Texto que trae el PDF:\n" + texto_pdf[:4000]})
    contenido_ia += [
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(datos).decode()}",
                                            "detail": "original"}}
        for mime, datos in imagenes
    ]
    cuerpo = {
        "model": os.getenv("SJ_SALUD_IA_MODELO") or os.getenv("SJ_IA_DEEPSEEK_MODELO") or "deepseek-flash",
        "messages": [{"role": "user", "content": contenido_ia}],
        "thinking": {"type": "disabled"},
        "reasoning_effort": "none",
        "temperature": 0,
        "max_tokens": 1200,
    }
    solicitud = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(cuerpo).encode(),
        headers={"Authorization": f"Bearer {clave}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(solicitud, timeout=60) as respuesta:
            salida = json.loads(respuesta.read())
        texto = salida["choices"][0]["message"]["content"].strip()
        texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto, flags=re.IGNORECASE)
        datos = json.loads(texto)
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("La IA no pudo leer el certificado. Revisá la conexión o la clave y volvé a intentar.") from exc
    transcripcion = str(datos.get("transcripcion") or "")
    resumen = str(datos.get("resumen") or "")
    dias = datos.get("dias_detectados")
    hallazgo_dias = re.search(r"\b(\d{1,3})\s*d[ií]as?\b", transcripcion, re.IGNORECASE)
    if dias is None and hallazgo_dias:
        dias = int(hallazgo_dias.group(1))
    normalizado = transcripcion.casefold()
    tipo_informado = str(datos.get("tipo_accidente") or "")
    if tipo_informado in {"NO_INFORMADO", "NO_ES_ACCIDENTE", "ACCIDENTE_LABORAL", "IN_ITINERE", "ACCIDENTE_A_REVISAR"}:
        tipo = tipo_informado
    elif "in itinere" in normalizado:
        tipo = "IN_ITINERE"
    elif "accidente laboral" in normalizado or "accidente de trabajo" in normalizado:
        tipo = "ACCIDENTE_LABORAL"
    elif "accidente" in normalizado:
        tipo = "ACCIDENTE_A_REVISAR"
    else:
        tipo = "NO_INFORMADO"
    return {
        **datos,
        "resumen": resumen,
        "dias_detectados": dias,
        "tipo_accidente": tipo,
        "texto_detectado": bool(transcripcion),
        "requiere_revision": True,
        "motor": "deepseek",
        "mensaje": "La IA leyó el manuscrito. Revisá los datos resaltados antes de guardar.",
    }


def _leer_imagen(contenido: bytes, extension: str) -> str:
    """OCR local con tesseract: esta lectura no envía el archivo fuera del servidor."""
    return leer_texto_imagen(contenido, extension)
