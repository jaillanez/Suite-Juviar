"""Importa teléfono-productor en Suite y publica una copia mínima en la DMZ."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from suite_juviar.plataforma.terceros.telefono import TelefonoInvalido
from suite_juviar.plataforma.terceros.telefono import normalizar as normalizar_estricto


def normalizar(telefono: str) -> str:
    """Compatibilidad del importador: una celda vacía sigue siendo vacía."""
    if not telefono:
        return ""
    return normalizar_estricto(telefono)


def importar(ruta: Path, responsable: str, conexion: psycopg.Connection) -> tuple[int, int, list[str]]:
    filas: list[tuple[str, str, str]] = []
    dudosos: list[str] = []
    invalidos = 0
    with ruta.open(newline="", encoding="utf-8-sig") as archivo:
        lector = csv.DictReader(archivo)
        if not lector.fieldnames or not {"telefono", "clientecuit"}.issubset(lector.fieldnames):
            raise ValueError("El CSV debe tener encabezados telefono,clientecuit")
        for registro in lector:
            telefono_crudo = registro.get("telefono", "")
            clientecuit = (registro.get("clientecuit") or "").strip()
            try:
                telefono = normalizar_estricto(telefono_crudo)
            except TelefonoInvalido:
                invalidos += 1
                conexion.execute(
                    """INSERT INTO terceros.contacto_pendiente
                       (telefono_crudo,nombre_excel,sucursal,motivo,candidatos)
                       VALUES (%s,%s,%s,'telefono_invalido',%s)""",
                    (
                        telefono_crudo,
                        registro.get("nombre") or registro.get("razonsocial") or "Sin nombre",
                        registro.get("suc") or registro.get("sucursal"),
                        Jsonb([]),
                    ),
                )
                continue
            if not clientecuit or len(clientecuit) > 40:
                invalidos += 1
                continue
            filas.append((telefono, clientecuit, responsable))
    with conexion.transaction(), conexion.cursor() as cursor:
        cursor.executemany(
            """INSERT INTO terceros.contacto_whatsapp
                   (telefono, clientecuit, origen, alta_por)
               VALUES (%s, %s, 'importacion_inicial', %s)
               ON CONFLICT (telefono, clientecuit) DO UPDATE SET activo = true""",
            filas,
        )
    return len(filas), invalidos, dudosos


def publicar(suite: psycopg.Connection, dsn_dmz: str) -> int:
    vinculos = suite.execute(
        "SELECT telefono, clientecuit, activo, tareas FROM terceros.contacto_whatsapp"
    ).fetchall()
    with psycopg.connect(dsn_dmz) as dmz, dmz.transaction(), dmz.cursor() as cursor:
        cursor.execute("DELETE FROM consulta.telefono_productor")
        cursor.executemany(
            """INSERT INTO consulta.telefono_productor
                   (telefono, clientecuit, activo, tareas) VALUES (%s, %s, %s, %s)""",
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
