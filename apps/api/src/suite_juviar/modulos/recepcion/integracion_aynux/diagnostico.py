"""Diagnóstico bloqueante de la vista Oracle antes de la primera importación.

Uso: python -m suite_juviar.modulos.recepcion.integracion_aynux.diagnostico chimbas
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta

from .config import Config
from .fuente_oracle import VISTA, FuenteOracle
from .modelo import COLUMNAS_ORIGEN


def _uno(cursor, sql: str, **parametros):
    cursor.execute(sql, parametros)
    return cursor.fetchone()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    config = Config.desde_entorno()
    sede = next((item for item in config.sedes if item.codigo == argv[1]), None)
    if sede is None:
        print(f"sede {argv[1]} no está en RECEPCION_SEDES_ACTIVAS")
        return 2

    fuente = FuenteOracle(sede, config.usuario, config.clave)
    bloqueante = False
    with fuente.conectar() as conexion, conexion.cursor() as cursor:
        print(f"== Servidor: {conexion.version}")
        print("\n== 1. Columnas de la vista")
        cursor.execute(f"SELECT * FROM {VISTA} WHERE 1 = 0")
        reales = {descripcion[0] for descripcion in cursor.description}
        faltan = set(COLUMNAS_ORIGEN) - reales
        print(f"   faltan: {sorted(faltan) or 'ninguna'}")
        print(f"   no usadas: {sorted(reales - set(COLUMNAS_ORIGEN)) or 'ninguna'}")
        bloqueante |= bool(faltan)

        print("\n== 2. Tipos de datos")
        cursor.execute(
            """SELECT column_name, data_type, data_length, data_precision, data_scale
               FROM all_tab_columns WHERE table_name = :vista ORDER BY column_id""",
            vista=VISTA,
        )
        for fila in cursor:
            print("   ", fila)

        print("\n== 3. ¿CIU sirve de clave?")
        total, con_ciu, distintos = _uno(
            cursor, f"SELECT COUNT(*), COUNT(CIU), COUNT(DISTINCT CIU) FROM {VISTA}"
        )
        print(f"   filas={total}  con CIU={con_ciu}  CIU distintos={distintos}")
        if con_ciu != total:
            print("   !! hay filas sin CIU")
            bloqueante = True
        if distintos != con_ciu:
            print("   !! CIU repetido. Primeros casos:")
            cursor.execute(
                f"""SELECT CIU, COUNT(*) FROM {VISTA}
                    GROUP BY CIU HAVING COUNT(*) > 1
                    ORDER BY COUNT(*) DESC FETCH FIRST 10 ROWS ONLY"""
            )
            for fila in cursor:
                print("     ", fila)
            bloqueante = True

        print("\n== 4. ¿ID se repite entre temporadas?")
        ids, distintos_id = _uno(cursor, f"SELECT COUNT(ID), COUNT(DISTINCT ID) FROM {VISTA}")
        print(f"   ID={ids}  distintos={distintos_id}  repetidos={ids - distintos_id}")

        print("\n== 5. Camiones en descarga (FECHA nula)")
        (en_curso,) = _uno(cursor, f"SELECT COUNT(*) FROM {VISTA} WHERE FECHA IS NULL")
        (neto_sin_fecha,) = _uno(
            cursor, f"SELECT COUNT(*) FROM {VISTA} WHERE FECHA IS NULL AND NETO IS NOT NULL"
        )
        (fecha_sin_neto,) = _uno(
            cursor, f"SELECT COUNT(*) FROM {VISTA} WHERE FECHA IS NOT NULL AND NETO IS NULL"
        )
        print(
            f"   en descarga={en_curso}  con neto pero sin fecha={neto_sin_fecha}  "
            f"con fecha pero sin neto={fecha_sin_neto}"
        )

        print("\n== 6. Rango de fechas")
        print("   ", _uno(cursor, f"SELECT MIN(FECHA), MAX(FECHA) FROM {VISTA}"))
        print("\n== 7. Escala de NETO y AZUCAR")
        print(
            "   NETO min/max/prom:",
            _uno(
                cursor, f"SELECT MIN(NETO), MAX(NETO), ROUND(AVG(NETO)) FROM {VISTA} WHERE NETO > 0"
            ),
        )
        print(
            "   AZUCAR min/max/prom:",
            _uno(
                cursor,
                f"SELECT MIN(AZUCAR), MAX(AZUCAR), ROUND(AVG(AZUCAR), 1) FROM {VISTA} WHERE AZUCAR > 0",
            ),
        )
        print("\n== 8. Productores sin NROINSCRIPTO")
        print("   ", _uno(cursor, f"SELECT COUNT(*) FROM {VISTA} WHERE NROINSCRIPTO IS NULL"))

    print("\n== 9. Tiempo de la consulta de ventana (15 días)")
    inicio = time.monotonic()
    # Oracle entrega FECHA sin zona; el filtro debe usar la misma semántica local.
    filas = fuente.leer_ventana(datetime.now() - timedelta(days=15))  # noqa: DTZ005
    print(f"   {len(filas)} filas en {time.monotonic() - inicio:.1f} s")
    print("\n== RESULTADO:", "BLOQUEANTE — no correr el worker" if bloqueante else "ok")
    return 1 if bloqueante else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
