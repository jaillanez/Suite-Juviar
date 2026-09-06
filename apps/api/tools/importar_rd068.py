"""Convierte la hoja 'Especificaciones' del Excel de ENAV en el catálogo del sistema.

Uso:
    python tools/importar_rd068.py "RD 062_11 Registro de Entrega...xls" \
        src/suite_juviar/modulos/rrhh_epp/data/catalogo_rd068.yaml

Existe para que, cuando RRHH publique la V 03 del RD 068/11, el catálogo se
regenere en un comando en vez de volver a tipear 145 filas a mano.

No inventa datos: lo que no está en el Excel sale vacío o nulo, y la
aplicación lo muestra como pendiente.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import xlrd
import yaml

# Valores de la columna de certificación que significan "no tiene".
SIN_CERTIFICACION = {"", "-", "n/a", "no", "no.", "s/d"}

# Familias, para agrupar en pantalla y para que la matriz pueda pedir
# "un protector auditivo de copa" sin atarse a una marca.
FAMILIAS = [
    (r"cartucho|filtro", "Filtros y cartuchos"),
    (r"semim|m[aá]scar|barbijo|respirador|mascarilla", "Protección respiratoria"),
    (r"calzado", "Calzado de seguridad"),
    (r"bota", "Botas de goma"),
    (r"ropa de trabajo", "Ropa de trabajo"),
    (r"guante", "Guantes"),
    (r"lentes", "Protección ocular"),
    (r"protector facial|visor|careta", "Protección facial"),
    (r"auditivo|endo aural", "Protección auditiva"),
    (r"delantal|polaina|manga", "Protección para soldadura"),
    (r"casco|arn[eé]s para casco", "Protección de cráneo"),
    (r"altura", "Protección contra caídas"),
    (r"lumbar", "Protección lumbar"),
    (r"bandolera|chaleco", "Alta visibilidad"),
]


def familia(producto: str) -> str:
    p = producto.lower()
    for patron, nombre in FAMILIAS:
        if re.search(patron, p):
            return nombre
    return "Otros"


def limpiar(v) -> str:
    return re.sub(r"\s+", " ", str(v)).strip()


def importar(origen: Path) -> dict:
    hoja = xlrd.open_workbook(origen).sheet_by_name("Especificaciones")
    vistos: set[str] = set()
    elementos = []

    for fila in range(6, hoja.nrows):
        orden = hoja.cell_value(fila, 0)
        producto = limpiar(hoja.cell_value(fila, 1)) or limpiar(hoja.cell_value(fila, 2))
        if orden == "" or not producto:
            continue

        codigo = str(int(orden))
        if codigo in vistos:
            # El Excel trae el 104 dos veces. No se pisa ni se descarta: se
            # marca para que RRHH lo resuelva en la próxima versión.
            codigo = f"{codigo}-B"
        vistos.add(codigo)

        cert_texto = limpiar(hoja.cell_value(fila, 5))
        elementos.append(
            {
                "codigo": codigo,
                "producto": producto,
                "familia": familia(producto + " " + limpiar(hoja.cell_value(fila, 3))),
                "tipo_modelo": limpiar(hoja.cell_value(fila, 3)),
                "marca": limpiar(hoja.cell_value(fila, 4)),
                "posee_certificacion": cert_texto.lower() not in SIN_CERTIFICACION,
                "certificacion": cert_texto or None,
                "destino_declarado": limpiar(hoja.cell_value(fila, 6)) or None,
                "unidad": "unidad",
                "vida_util_dias": None,   # el RD 068/11 no la trae. Pendiente de HyS.
            }
        )

    return {
        "version": 1,
        "norma": "RD 068/11",
        "version_norma": "V 02 — Septiembre 2023",
        "origen": origen.name,
        "estado": "IMPORTADO_SIN_VALIDAR",
        "dueno_del_dato": "Recursos Humanos / Higiene y Seguridad",
        "elementos": elementos,
    }


if __name__ == "__main__":
    origen = Path(sys.argv[1])
    destino = Path(sys.argv[2])
    datos = importar(origen)
    destino.write_text(
        "# Generado por apps/api/tools/importar_rd068.py — no editar a mano.\n"
        "# Para actualizar: publicar la nueva versión del Excel y volver a correr el importador.\n"
        + yaml.safe_dump(datos, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    print(f"{len(datos['elementos'])} elementos escritos en {destino}")
