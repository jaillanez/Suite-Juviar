"""Genera una constancia PDF de muestra para revisar el adaptador simulado."""

from __future__ import annotations

import base64
from datetime import date
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from suite_juviar.modulos.rrhh_epp.mvp import construir


def firma_muestra() -> str:
    imagen = Image.new("RGB", (700, 160), "white")
    dibujo = ImageDraw.Draw(imagen)
    dibujo.line([(40, 110), (150, 45), (260, 120), (390, 50), (610, 105)], fill="#141a1f", width=7)
    salida = BytesIO()
    imagen.save(salida, format="PNG")
    return "data:image/png;base64," + base64.b64encode(salida.getvalue()).decode("ascii")


def generar(destino: Path) -> None:
    contenedor = construir(entorno="prueba", fuente_legajos="yaml", ruta_base=":memory:")
    entrega = contenedor.registrar_entrega.ejecutar(
        numero_legajo="1077",
        items=[{"codigo": "69", "item_codigo": "SIM-69-02", "cantidad": 1}],
        metodo_firma="TRAZO_TABLET",
        evidencia_firma=firma_muestra(),
        usuario_deposito="1210",
        fecha=date(2026, 3, 12),
        id_entrega="MUESTRA-RD062-11",
    )
    documento = contenedor.obtener_constancia_pdf.ejecutar(entrega.id)
    if documento is None:
        raise RuntimeError("No se pudo generar la constancia de muestra.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(documento.contenido)


if __name__ == "__main__":
    generar(Path("output/pdf/constancia_epp_muestra.pdf"))
