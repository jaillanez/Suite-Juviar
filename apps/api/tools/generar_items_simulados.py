"""Genera el catálogo de ítems SIMULADO mientras no llegue el Excel maestro.

Uso desde la raíz del repositorio:
   
    .venv/bin/python apps/api/tools/generar_items_simulados.py

El resultado se reemplaza completo cuando Higiene y Seguridad entregue los
códigos internos reales. No usar estos códigos para una entrega productiva.
"""

from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
CATALOGO = RAIZ / "src/suite_juviar/modulos/rrhh_epp/data/catalogo_rd068.yaml"
SALIDA = RAIZ / "src/suite_juviar/modulos/rrhh_epp/data/catalogo_items.yaml"


def generar() -> None:
    fuente = yaml.safe_load(CATALOGO.read_text(encoding="utf-8"))
    items: list[dict[str, object]] = []
    for elemento in fuente["elementos"]:
        codigo = str(elemento["codigo"])
        for numero in range(1, 4):
            items.append(
                {
                    "codigo_interno": f"SIM-{codigo}-{numero:02d}",
                    "elemento_codigo": codigo,
                    "marca": elemento.get("marca") or "SIN_DATO",
                    "modelo": elemento.get("tipo_modelo") or "SIN_DATO",
                    "talle": "SIN_DATO",
                    "color": "SIN_DATO",
                    "estado": "SIMULADO",
                }
            )
    documento = {
        "version": 1,
        "dueno_dato": "Higiene y Seguridad",
        "estado": "SIMULADO",
        "nota": (
            "Generado sin el Excel de códigos internos. Reemplazar el archivo completo; "
            "no editar ni usar en producción."
        ),
        "items": items,
    }
    cabecera = (
        "# ARCHIVO GENERADO por apps/api/tools/generar_items_simulados.py\n"
        "# Datos SIMULADOS: no representan códigos internos ni variantes reales de ENAV.\n"
    )
    SALIDA.write_text(
        cabecera + yaml.safe_dump(documento, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    generar()
