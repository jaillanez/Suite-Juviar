"""Imagen de estadísticas para WhatsApp.

Se mira en un celular, con el pulgar, muchas veces al sol. De ahí las
decisiones: una sola columna, números grandes, un color por gráfico (la
identidad la dan las etiquetas, no el color) y ninguna leyenda.

Cada gráfico lleva su valor escrito al lado de la barra: quien lo mire no
tiene que estimar contra una grilla.
"""
from __future__ import annotations

import io
from datetime import UTC, datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from .estadisticas import Resumen, formatear_kg

SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_SUAVE = "#52514e"
SERIE = "#2a78d6"     # validado contra la superficie clara
GRILLA = "#e3e2dd"
ANCHO_PX, ALTO_PX, PPP = 1080, 1350, 100
MAXIMO_DIAS_BARRAS = 31   # con más días, las barras no se distinguen en un celular


def _miles(valor: float, _pos: int = 0) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _sin_marco(ejes) -> None:
    for lado in ("top", "right", "left", "bottom"):
        ejes.spines[lado].set_visible(False)
    ejes.tick_params(length=0, colors=TINTA_SUAVE, labelsize=15)


def generar(resumen: Resumen, titular: str, cuenta: str, periodo: str) -> bytes:
    figura = plt.figure(figsize=(ANCHO_PX / PPP, ALTO_PX / PPP), dpi=PPP, facecolor=SUPERFICIE)
    grilla = figura.add_gridspec(
        3, 1, height_ratios=[0.62, 0.95, 1.25], hspace=0.38,
        left=0.09, right=0.97, top=0.95, bottom=0.08,
    )

    # --- Encabezado: el número que el productor busca primero ---------------
    cabecera = figura.add_subplot(grilla[0])
    cabecera.axis("off")
    cabecera.text(0, 1.0, titular.strip().rstrip("."), fontsize=21, color=TINTA,
                  weight="bold", va="top")
    cabecera.text(0, 0.78, f"Cuenta {cuenta} · {periodo}", fontsize=15, color=TINTA_SUAVE, va="top")
    cabecera.text(0, 0.42, formatear_kg(resumen.total_kg), fontsize=46, color=TINTA,
                  weight="bold", va="center")
    detalle = f"{resumen.entregas} entrega{'s' if resumen.entregas != 1 else ''}"
    if resumen.entregas:
        detalle += f" · promedio {formatear_kg(resumen.promedio_por_entrega)}"
    if resumen.azucar_promedio is not None:
        detalle += f" · azúcar {resumen.azucar_promedio:g} g/l"
    cabecera.text(0, 0.06, detalle, fontsize=15, color=TINTA_SUAVE, va="center")

    # --- Kilos por variedad -------------------------------------------------
    variedades = figura.add_subplot(grilla[1], facecolor=SUPERFICIE)
    _sin_marco(variedades)
    if resumen.por_variedad:
        nombres = [v for v, _ in resumen.por_variedad][::-1]
        valores = [k for _, k in resumen.por_variedad][::-1]
        posiciones = list(range(len(nombres)))
        variedades.barh(posiciones, valores, color=SERIE, height=0.42)
        variedades.set_yticks([])
        variedades.set_xticks([])
        tope = max(valores)
        for posicion, nombre, valor in zip(posiciones, nombres, valores, strict=True):
            variedades.text(0, posicion + 0.34, nombre, va="bottom", fontsize=16, color=TINTA)
            variedades.text(valor + tope * 0.015, posicion, formatear_kg(valor),
                            va="center", fontsize=15, color=TINTA)
        variedades.set_xlim(0, tope * 1.30)
        variedades.set_ylim(-0.6, len(nombres) - 0.25)
    variedades.set_title("Kilos por variedad", fontsize=17, color=TINTA,
                         loc="left", pad=14, weight="bold")

    # --- Entregas en el tiempo ---------------------------------------------
    tiempo = figura.add_subplot(grilla[2], facecolor=SUPERFICIE)
    _sin_marco(tiempo)
    tiempo.grid(axis="y", color=GRILLA, linewidth=1)
    tiempo.set_axisbelow(True)
    if resumen.por_dia:
        dias = [d for d, _ in resumen.por_dia]
        kilos = [k for _, k in resumen.por_dia]
        if len(dias) <= MAXIMO_DIAS_BARRAS:
            barras = tiempo.bar(dias, kilos, color=SERIE, width=0.7)
            for barra, kilos_dia in zip(barras, kilos, strict=True):
                tiempo.annotate(
                    _miles(kilos_dia),
                    (barra.get_x() + barra.get_width() / 2, barra.get_height()),
                    xytext=(0, 4),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    rotation=90,
                    fontsize=9,
                    color=TINTA_SUAVE,
                )
            titulo = "Kilos por día"
        else:
            acumulado, suma = [], 0
            for k in kilos:
                suma += k
                acumulado.append(suma)
            tiempo.plot(dias, acumulado, color=SERIE, linewidth=2.5)
            tiempo.fill_between(dias, acumulado, color=SERIE, alpha=0.12)
            titulo = "Kilos acumulados"
        tiempo.yaxis.set_major_formatter(FuncFormatter(_miles))
        tiempo.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=6))
        tiempo.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
        tiempo.margins(x=0.04)
    else:
        titulo = "Kilos por día"
        tiempo.text(0.5, 0.5, "Sin entregas en el período", ha="center",
                    fontsize=16, color=TINTA_SUAVE)
        tiempo.set_xticks([])
        tiempo.set_yticks([])
    tiempo.set_title(titulo, fontsize=17, color=TINTA, loc="left", pad=14, weight="bold")

    figura.text(0.09, 0.02, f"Generado el {datetime.now(UTC):%d/%m/%Y} · Juviar-ENAV",
                fontsize=12, color=TINTA_SUAVE)

    memoria = io.BytesIO()
    figura.savefig(memoria, format="png", facecolor=SUPERFICIE)
    plt.close(figura)
    return memoria.getvalue()
