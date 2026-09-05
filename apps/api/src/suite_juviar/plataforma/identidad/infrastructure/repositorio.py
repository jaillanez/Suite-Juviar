"""Lectura del maestro de legajos de Nexus a través de una vista SQL.

Base Común §4.2: se accede por VPN con Vistas y Stored Procedures en SQL Server,
no con una API REST. La vista expone solo los campos que el sistema necesita;
el rol de la aplicación no tiene permiso de escritura sobre las tablas base.

Este repositorio implementa `RepositorioLegajos`, que no declara ningún método
de escritura. No es que "no lo usemos": no existe.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from suite_juviar.plataforma.identidad.domain.entidades import (
    Empresa,
    Legajo,
    NumeroLegajo,
    TipoVinculo,
)

VISTA = "vw_legajo_suite"


class RepositorioLegajosSQL:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def obtener(self, numero: NumeroLegajo) -> Legajo | None:
        fila = (
            await self._session.execute(
                text(f"SELECT * FROM {VISTA} WHERE numero_legajo = :n"),
                {"n": numero.valor},
            )
        ).mappings().first()
        return self._armar(fila) if fila else None

    async def buscar_por_dni(self, dni: str) -> Legajo | None:
        fila = (
            await self._session.execute(
                text(f"SELECT * FROM {VISTA} WHERE dni = :d"), {"d": dni}
            )
        ).mappings().first()
        return self._armar(fila) if fila else None

    async def listar_por_sector(
        self, sector: str, empresa: Empresa, solo_activos: bool = True
    ) -> list[Legajo]:
        filas = (
            await self._session.execute(
                text(
                    f"SELECT * FROM {VISTA} "
                    "WHERE sector = :s AND empresa = :e "
                    "AND (:a = 0 OR activo = 1)"
                ),
                {"s": sector, "e": empresa.value, "a": int(solo_activos)},
            )
        ).mappings().all()
        return [self._armar(f) for f in filas]

    @staticmethod
    def _armar(fila) -> Legajo:
        return Legajo(
            numero=NumeroLegajo(fila["numero_legajo"]),
            nombre=fila["nombre"],
            apellido=fila["apellido"],
            dni=fila["dni"],
            puesto=fila["puesto"],
            sector=fila["sector"],
            empresa=Empresa(fila["empresa"]),
            tipo_vinculo=TipoVinculo(fila["tipo_vinculo"]),
            fecha_ingreso=fila["fecha_ingreso"],
            activo=bool(fila["activo"]),
        )
