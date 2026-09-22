"""Carga o elimina vínculos ficticios identificables para el simulador."""

from __future__ import annotations

import os
import sys

import psycopg

PREFIJO = "549000000"


def publicar(suite: psycopg.Connection, dsn_dmz: str) -> int:
    vinculos = suite.execute(
        "SELECT telefono, clientecuit, activo FROM terceros.contacto_whatsapp"
    ).fetchall()
    with psycopg.connect(dsn_dmz) as dmz, dmz.transaction(), dmz.cursor() as cursor:
        cursor.execute("DELETE FROM consulta.telefono_productor")
        cursor.executemany(
            """INSERT INTO consulta.telefono_productor
                   (telefono, clientecuit, activo) VALUES (%s, %s, %s)""",
            vinculos,
        )
    return len(vinculos)


def main(argumentos: list[str]) -> int:
    dsn_suite = os.environ["RECEPCION_DSN_SUITE"]
    dsn_dmz = os.environ["RECEPCION_DSN_DMZ"]
    with psycopg.connect(dsn_suite) as conexion:
        if argumentos[1:] == ["--borrar"]:
            borrados = conexion.execute(
                "DELETE FROM terceros.contacto_whatsapp WHERE origen = 'prueba'"
            ).rowcount
            print(f"borrados: {borrados}")
        else:
            cantidad = int(argumentos[1]) if len(argumentos) > 1 else 5
            if not 1 <= cantidad <= 20:
                raise ValueError("la cantidad debe estar entre 1 y 20")
            productores = [
                fila[0]
                for fila in conexion.execute(
                    """SELECT clientecuit FROM recepcion.descarga
                       WHERE clientecuit IS NOT NULL AND estado = 'descargado'
                       GROUP BY clientecuit ORDER BY count(*) DESC LIMIT %s""",
                    (cantidad,),
                ).fetchall()
            ]
            for indice, inscripto in enumerate(productores, start=1):
                telefono = f"{PREFIJO}{indice:04d}"
                conexion.execute(
                    """INSERT INTO terceros.contacto_whatsapp
                           (telefono, clientecuit, origen, alta_por)
                       VALUES (%s, %s, 'prueba', 'simulador')
                       ON CONFLICT (telefono, clientecuit)
                       DO UPDATE SET activo = true""",
                    (telefono, inscripto),
                )
                print(f"{telefono} -> {inscripto}")
        conexion.commit()
        publicados = publicar(conexion, dsn_dmz)
        print(f"publicados en DMZ: {publicados}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
