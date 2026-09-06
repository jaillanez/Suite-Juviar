"""Genera stock SIMULADO para probar el circuito hasta recibir el inventario real."""

from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
ITEMS = RAIZ / "src/suite_juviar/modulos/rrhh_epp/data/catalogo_items.yaml"
SALIDA = RAIZ / "src/suite_juviar/modulos/rrhh_epp/data/stock_inicial_simulado.yaml"


def generar() -> None:
    fuente = yaml.safe_load(ITEMS.read_text(encoding="utf-8")) or {}
    stock = [
        {
            "item_codigo": item["codigo_interno"],
            "disponible": 100,
            "minimo": 20,
            "estado": "SIMULADO",
        }
        for item in fuente.get("items") or []
    ]
    documento = {
        "version": 1,
        "dueno_dato": "Depósito",
        "estado": "SIMULADO",
        "nota": "Cantidades ficticias para pruebas. Reemplazar por inventario definido por Depósito.",
        "stock": stock,
    }
    SALIDA.write_text(
        "# ARCHIVO GENERADO - STOCK SIMULADO, PROHIBIDO EN PRODUCCION\n"
        + yaml.safe_dump(documento, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    generar()
