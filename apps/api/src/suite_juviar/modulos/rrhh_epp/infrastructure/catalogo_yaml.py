"""Catálogo RD 068/11 y matriz Puesto vs. EPP desde YAML.

Estos dos archivos son provisorios pero el adaptador no: cuando llegue el
catálogo real, se reemplaza el contenido del YAML, o se escribe un adaptador
contra la tabla de PostgreSQL, y el dominio sigue igual.

Al cargar valida que la matriz no apunte a códigos inexistentes. Es preferible
que la aplicación no arranque a que un operario vea en pantalla un elemento
que no existe.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..domain.modelos_mvp import ElementoEPP, RequisitoEPP

FRECUENCIAS = {"SEMESTRAL", "ANUAL", "A_DEMANDA"}
TEMPORADAS = {"VERANO", "INVIERNO", "TODO_EL_ANIO"}


class ErrorDeCatalogo(Exception):
    pass


class CatalogoYAML:
    def __init__(self, ruta_catalogo: str | Path, ruta_matriz: str | Path) -> None:
        self._ruta_catalogo = Path(ruta_catalogo)
        self._ruta_matriz = Path(ruta_matriz)
        self._elementos: dict[str, ElementoEPP] = {}
        self._matriz: dict[str, list[RequisitoEPP]] = {}
        self._estado_matriz = "DESCONOCIDO"
        self._cargar_catalogo()
        self._cargar_matriz()

    @property
    def estado_matriz(self) -> str:
        """PROVISORIA mientras Higiene y Seguridad no la valide."""
        return self._estado_matriz

    def _cargar_catalogo(self) -> None:
        datos = yaml.safe_load(self._ruta_catalogo.read_text(encoding="utf-8")) or {}
        for fila in datos.get("elementos") or []:
            codigo = str(fila["codigo"]).strip()
            if codigo in self._elementos:
                raise ErrorDeCatalogo(f"Código {codigo} duplicado en el catálogo.")
            self._elementos[codigo] = ElementoEPP(
                codigo=codigo,
                producto=str(fila["producto"]),
                tipo_modelo=str(fila.get("tipo_modelo") or ""),
                marca=str(fila.get("marca") or ""),
                posee_certificacion=bool(fila.get("posee_certificacion")),
                certificacion=fila.get("certificacion"),
                unidad=str(fila.get("unidad") or "unidad"),
                vida_util_dias=fila.get("vida_util_dias"),
            )
        if not self._elementos:
            raise ErrorDeCatalogo(f"{self._ruta_catalogo.name} está vacío.")

    def _cargar_matriz(self) -> None:
        datos = yaml.safe_load(self._ruta_matriz.read_text(encoding="utf-8")) or {}
        self._estado_matriz = str(datos.get("estado") or "DESCONOCIDO")
        for puesto, definicion in (datos.get("puestos") or {}).items():
            requisitos: list[RequisitoEPP] = []
            for fila in definicion.get("elementos") or []:
                codigo = str(fila["codigo"]).strip()
                if codigo not in self._elementos:
                    raise ErrorDeCatalogo(
                        f"La matriz del puesto {puesto} pide el código {codigo}, "
                        f"que no está en {self._ruta_catalogo.name}."
                    )
                frecuencia = str(fila.get("frecuencia") or "A_DEMANDA")
                temporada = str(fila.get("temporada") or "TODO_EL_ANIO")
                if frecuencia not in FRECUENCIAS:
                    raise ErrorDeCatalogo(f"Frecuencia inválida en {puesto}/{codigo}: {frecuencia}")
                if temporada not in TEMPORADAS:
                    raise ErrorDeCatalogo(f"Temporada inválida en {puesto}/{codigo}: {temporada}")
                requisitos.append(
                    RequisitoEPP(
                        codigo=codigo,
                        cantidad=int(fila.get("cantidad") or 1),
                        frecuencia=frecuencia,
                        temporada=temporada,
                        obligatorio=bool(fila.get("obligatorio", True)),
                    )
                )
            self._matriz[str(puesto).strip()] = requisitos

    def obtener_elemento(self, codigo: str) -> ElementoEPP | None:
        return self._elementos.get(str(codigo).strip())

    def listar_elementos(self) -> list[ElementoEPP]:
        return sorted(self._elementos.values(), key=lambda e: e.codigo)

    def requisitos_de_puesto(self, puesto_codigo: str) -> list[RequisitoEPP]:
        return list(self._matriz.get(str(puesto_codigo).strip(), []))
