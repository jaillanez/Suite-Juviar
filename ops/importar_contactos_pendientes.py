"""Carga la revisión privada en la bandeja y no conserva el archivo fuente."""
from __future__ import annotations

import argparse
import csv
import os
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import psycopg
from openpyxl import load_workbook
from psycopg.types.json import Jsonb


def nombre(valor: object) -> str:
    texto = " ".join(str(valor or "").upper().split())
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def telefonos_crudos(valor: object) -> list[str]:
    return [p.strip() for p in re.split(r"[\n;,/]+", str(valor or "")) if p.strip()]


def motivo(bruto: str) -> str:
    if "telefono" in bruto and ("ambiguo" in bruto or "sin_telefono" in bruto):
        return "telefono_invalido"
    if "varios" in bruto or "conflicto" in bruto:
        return "ambiguo"
    return "sin_coincidencia"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", type=Path, required=True)
    parser.add_argument("--excel", type=Path, required=True)
    parser.add_argument("--dsn", default=os.environ.get("RECEPCION_DSN_SUITE"))
    args = parser.parse_args()
    if not args.dsn:
        parser.error("falta --dsn o RECEPCION_DSN_SUITE")

    libro = load_workbook(args.excel, read_only=True, data_only=True)
    hoja = libro["CONTACTOS"]
    originales = {
        numero: list(valores)
        for numero, valores in enumerate(
            hoja.iter_rows(min_row=2, max_col=4, values_only=True), start=2
        )
    }
    with args.revision.open(newline="", encoding="utf-8") as archivo:
        revision = list(csv.DictReader(archivo))

    with psycopg.connect(args.dsn) as cn:
        productores: dict[str, dict[str, str]] = defaultdict(dict)
        for razon, cuit in cn.execute(
            """SELECT DISTINCT razonsocial,clientecuit FROM recepcion.descarga
               WHERE clientecuit IS NOT NULL AND razonsocial IS NOT NULL"""
        ):
            productores[nombre(razon)][str(cuit)] = str(razon)
        insertados = 0
        for fila in revision:
            numero = int(fila["fila_excel"])
            suc, razon, primario, alternativo = originales[numero]
            crudos = telefonos_crudos(primario) + telefonos_crudos(alternativo)
            if not crudos:
                crudos = [fila.get("telefonos") or fila.get("observacion") or "Sin teléfono"]
            candidatos = [
                {"clientecuit": cuit, "razonsocial": razon_db}
                for cuit, razon_db in productores.get(nombre(razon), {}).items()
            ]
            for crudo in dict.fromkeys(crudos):
                cn.execute(
                    """INSERT INTO terceros.contacto_pendiente
                       (telefono_crudo,nombre_excel,sucursal,motivo,candidatos)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (
                        crudo,
                        str(razon or fila.get("productor") or "Sin nombre"),
                        str(suc or fila.get("suc") or ""),
                        motivo(fila.get("motivo", "")),
                        Jsonb(candidatos),
                    ),
                )
                insertados += 1
    print(f"filas_revision={len(revision)} pendientes_insertados={insertados}")


if __name__ == "__main__":
    main()
