"""Escritura de celdas de Excel sin que un texto cargado por alguien se vuelva fórmula."""

from __future__ import annotations


def escribir(hoja, fila: int, columna: int, valor):
    """Como `hoja.cell(fila, columna, valor)`, pero un texto que empieza con «=» queda como texto."""
    celda = hoja.cell(fila, columna, valor)
    if isinstance(valor, str):
        celda.data_type = "s"
    return celda
