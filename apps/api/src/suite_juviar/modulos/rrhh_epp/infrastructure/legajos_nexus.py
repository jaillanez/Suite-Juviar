"""Fuente de legajos REAL: Vista de solo lectura en Nexus (SQL Server, Santa Fe).

Está sin terminar a propósito. Falta lo que todavía no tenemos:
  - los parámetros y credenciales de la VPN,
  - que exista la Vista dbo.vw_legajos_activos (ver sql/vw_legajos_activos.sql),
  - el driver ODBC instalado en el servidor donde corra la aplicación.

Cuando esas tres cosas estén, se completa `_conectar`, se corre
`tests/test_contrato_legajos.py` apuntando a esta clase y, si pasa, se cambia
FUENTE_LEGAJOS=nexus. El resto del módulo no se toca.
"""

from __future__ import annotations

from ..domain.modelos_mvp import Legajo

CONSULTA_BASE = """
SELECT legajo, nombre, apellido, dni, puesto_codigo, puesto,
       sector_codigo, sector, empresa, tipo_vinculo, activo
FROM dbo.vw_legajos_activos
"""


class LegajosNexusSQLServer:
    def __init__(self, cadena_conexion: str) -> None:
        self._cadena = cadena_conexion

    @property
    def fuente(self) -> str:
        return "NEXUS"

    def _conectar(self):
        # import pyodbc
        # return pyodbc.connect(self._cadena, readonly=True, timeout=5)
        raise NotImplementedError(
            "Falta la conexión a Nexus: VPN, credenciales y Vista "
            "dbo.vw_legajos_activos. Mientras tanto se usa FUENTE_LEGAJOS=yaml."
        )

    @staticmethod
    def _a_legajo(fila) -> Legajo:
        return Legajo(
            legajo=str(fila.legajo).strip(),
            nombre=fila.nombre,
            apellido=fila.apellido,
            dni=str(fila.dni).strip(),
            puesto_codigo=fila.puesto_codigo,
            puesto=fila.puesto,
            sector_codigo=fila.sector_codigo,
            sector=fila.sector,
            empresa=fila.empresa,
            tipo_vinculo=fila.tipo_vinculo,
            activo=bool(fila.activo),
        )

    def obtener(self, legajo: str) -> Legajo | None:
        with self._conectar() as cn:
            cursor = cn.cursor()
            cursor.execute(CONSULTA_BASE + " WHERE legajo = ?", str(legajo).strip())
            fila = cursor.fetchone()
            return self._a_legajo(fila) if fila else None

    def buscar(self, texto: str, limite: int = 20) -> list[Legajo]:
        patron = f"%{(texto or '').strip()}%"
        with self._conectar() as cn:
            cursor = cn.cursor()
            cursor.execute(
                CONSULTA_BASE
                + " WHERE activo = 1 AND (legajo LIKE ? OR dni LIKE ? OR apellido LIKE ?)"
                  " ORDER BY apellido, nombre",
                patron, patron, patron,
            )
            return [self._a_legajo(f) for f in cursor.fetchmany(limite)]
