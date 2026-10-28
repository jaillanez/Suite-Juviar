"""Fuente de legajos SIMULADA, leyendo un YAML.

Existe sólo porque todavía no hay VPN ni Vista en Nexus. Devuelve exactamente
los mismos campos que va a devolver la Vista, así el reemplazo es cambiar una
variable de entorno y nada más.

Esta clase NO puede usarse en producción: config.py lo impide.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..domain.modelos_mvp import Legajo

CAMPOS = (
    "legajo",
    "nombre",
    "apellido",
    "dni",
    "puesto_codigo",
    "puesto",
    "sector_codigo",
    "sector",
    "empresa",
    "tipo_vinculo",
    "activo",
)


class ErrorDeDatos(Exception):
    pass


class LegajosYAML:
    def __init__(self, ruta: str | Path) -> None:
        self._ruta = Path(ruta)
        self._por_numero: dict[str, Legajo] = {}
        self._cargar()

    @property
    def fuente(self) -> str:
        return "SIMULADA"

    def _cargar(self) -> None:
        if not self._ruta.exists():
            raise ErrorDeDatos(f"No se encuentra el archivo de legajos: {self._ruta}")
        datos = yaml.safe_load(self._ruta.read_text(encoding="utf-8")) or {}
        filas = datos.get("legajos") or []
        if not filas:
            raise ErrorDeDatos(f"{self._ruta} no tiene legajos cargados.")

        for i, fila in enumerate(filas, start=1):
            faltantes = [c for c in CAMPOS if c not in fila]
            if faltantes:
                raise ErrorDeDatos(
                    f"Legajo #{i} en {self._ruta.name}: faltan los campos "
                    f"{', '.join(faltantes)}. La Vista de Nexus tiene que "
                    f"devolver estas {len(CAMPOS)} columnas."
                )
            numero = str(fila["legajo"]).strip()
            if numero in self._por_numero:
                raise ErrorDeDatos(f"El legajo {numero} está duplicado en {self._ruta.name}.")
            self._por_numero[numero] = Legajo(
                legajo=numero,
                nombre=str(fila["nombre"]),
                apellido=str(fila["apellido"]),
                dni=str(fila["dni"]),
                puesto_codigo=str(fila["puesto_codigo"]),
                puesto=str(fila["puesto"]),
                sector_codigo=str(fila["sector_codigo"]),
                sector=str(fila["sector"]),
                empresa=str(fila["empresa"]),
                tipo_vinculo=str(fila["tipo_vinculo"]),
                activo=bool(fila["activo"]),
            )

    def obtener(self, legajo: str) -> Legajo | None:
        return self._por_numero.get(str(legajo).strip())

    def listar_activos(self) -> list[Legajo]:
        return sorted(
            (persona for persona in self._por_numero.values() if persona.activo),
            key=lambda persona: (persona.apellido, persona.nombre),
        )

    def buscar(self, texto: str, limite: int = 20) -> list[Legajo]:
        t = (texto or "").strip().lower()
        if not t:
            return []
        encontrados = [
            p
            for p in self._por_numero.values()
            if p.activo
            and (
                t in p.legajo.lower()
                or t in p.dni.lower()
                or t in p.apellido.lower()
                or t in p.nombre.lower()
            )
        ]
        encontrados.sort(key=lambda p: (p.apellido, p.nombre))
        return encontrados[:limite]
