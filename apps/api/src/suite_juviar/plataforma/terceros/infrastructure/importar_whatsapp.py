"""Importa teléfono-productor en Suite y publica una copia mínima en la DMZ."""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

import psycopg


def normalizar(telefono: str) -> str:
    return re.sub(r"\D", "", telefono or "")


def importar(ruta: Path, responsable: str, conexion: psycopg.Connection) -> tuple[int, int, list[str]]:
    filas: list[tuple[str, str, str]] = []
    dudosos: list[str] = []
    invalidos = 0
    with ruta.open(newline="", encoding="utf-8-sig") as archivo:
        lector = csv.DictReader(archivo)
        if not lector.fieldnames or not {"telefono", "nroinscripto"}.issubset(lector.fieldnames):
            raise ValueError("El CSV debe tener encabezados telefono,nroinscripto")
        for registro in lector:
            telefono = normalizar(registro.get("telefono", ""))
            inscripto = (registro.get("nroinscripto") or "").strip()
            if not 8 <= len(telefono) <= 20 or not inscripto or len(inscripto) > 40:
                invalidos += 1
                continue
            if not telefono.startswith("549"):
                dudosos.append(telefono)
            filas.append((telefono, inscripto, responsable))
    with conexion.transaction(), conexion.cursor() as cursor:
        cursor.executemany(
            """INSERT INTO terceros.contacto_whatsapp
                   (telefono, nroinscripto, origen, alta_por)
               VALUES (%s, %s, 'importacion_inicial', %s)
               ON CONFLICT (telefono, nroinscripto) DO UPDATE SET activo = true""",
            filas,
        )
    return len(filas), invalidos, dudosos


def publicar(suite: psycopg.Connection, dsn_dmz: str) -> int:
    vinculos = suite.execute(
        "SELECT telefono, nroinscripto, activo FROM terceros.contacto_whatsapp"
    ).fetchall()
    with psycopg.connect(dsn_dmz) as dmz, dmz.transaction(), dmz.cursor() as cursor:
        cursor.execute("DELETE FROM consulta.telefono_productor")
        cursor.executemany(
            """INSERT INTO consulta.telefono_productor
                   (telefono, nroinscripto, activo) VALUES (%s, %s, %s)""",
            vinculos,
        )
    return len(vinculos)


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?", type=Path)
    parser.add_argument("--por")
    parser.add_argument("--solo-publicar", action="store_true")
    opciones = parser.parse_args(argumentos)
    with psycopg.connect(os.environ["RECEPCION_DSN_SUITE"]) as suite:
        if not opciones.solo_publicar:
            if not opciones.csv or not opciones.por:
                parser.error("hace falta el CSV y --por")
            cantidad, invalidos, dudosos = importar(opciones.csv, opciones.por, suite)
            print(
                f"importados={cantidad} invalidos={invalidos} "
                f"fuera_de_formato_549={len(dudosos)}"
            )
            for telefono in dudosos[:20]:
                print("   revisar:", telefono)
        publicados = publicar(suite, os.environ["RECEPCION_DSN_DMZ"])
        print(f"publicados en DMZ: {publicados}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
