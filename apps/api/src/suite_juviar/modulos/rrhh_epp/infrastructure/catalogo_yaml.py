"""Catálogo RD 068/11 y matriz sector + puesto desde YAML.

El catálogo se regenera desde el Excel de RRHH. La matriz usa como base los 19
sectores del esquema de ENAV y agrega requisitos específicos por puesto.

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
PESO = {"BASE": 0, "SECTOR": 1, "PUESTO": 2}


def _orden_codigo(codigo: str) -> tuple[int, str]:
    """Orden natural para códigos textuales: 9, 10, 104, 104-B, 114."""
    numero, _, sufijo = codigo.partition("-")
    return (int(numero) if numero.isdigit() else 9999, sufijo)


class ErrorDeCatalogo(Exception):
    pass


class CatalogoYAML:
    def __init__(self, ruta_catalogo: str | Path, ruta_matriz: str | Path) -> None:
        self._ruta_catalogo = Path(ruta_catalogo)
        self._ruta_matriz = Path(ruta_matriz)
        self._elementos: dict[str, ElementoEPP] = {}
        self._base: list[RequisitoEPP] = []
        self._sectores: dict[str, dict] = {}
        self._puestos: dict[str, list[RequisitoEPP]] = {}
        self._estado_matriz = "DESCONOCIDO"
        self._version_norma = ""
        self._cargar_catalogo()
        self._cargar_matriz()

    @property
    def estado_matriz(self) -> str:
        """PROPUESTA_SIN_VALIDAR mientras Higiene y Seguridad no la firme."""
        return self._estado_matriz

    @property
    def version_norma(self) -> str:
        return self._version_norma

    @property
    def sectores_conocidos(self) -> list[str]:
        return sorted(self._sectores)

    def _cargar_catalogo(self) -> None:
        datos = yaml.safe_load(self._ruta_catalogo.read_text(encoding="utf-8")) or {}
        self._version_norma = str(datos.get("version_norma") or "")
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
                familia=str(fila.get("familia") or "Otros"),
                destino_declarado=fila.get("destino_declarado"),
                criterio_vida_util=str(fila.get("criterio_vida_util") or ""),
            )
        if not self._elementos:
            raise ErrorDeCatalogo(f"{self._ruta_catalogo.name} está vacío.")

    def _leer_requisitos(self, filas: list[dict] | None, contexto: str) -> list[RequisitoEPP]:
        requisitos: list[RequisitoEPP] = []
        for fila in filas or []:
            codigo = str(fila["codigo"]).strip()
            if codigo not in self._elementos:
                raise ErrorDeCatalogo(
                    f"{contexto} pide el código {codigo}, que no está en "
                    f"{self._ruta_catalogo.name}."
                )
            frecuencia = str(fila.get("frecuencia") or "A_DEMANDA")
            temporada = str(fila.get("temporada") or "TODO_EL_ANIO")
            if frecuencia not in FRECUENCIAS:
                raise ErrorDeCatalogo(
                    f"{contexto}/{codigo}: frecuencia inválida '{frecuencia}'."
                )
            if temporada not in TEMPORADAS:
                raise ErrorDeCatalogo(
                    f"{contexto}/{codigo}: temporada inválida '{temporada}'."
                )
            requisitos.append(
                RequisitoEPP(
                    codigo=codigo,
                    cantidad=int(fila.get("cantidad") or 1),
                    frecuencia=frecuencia,
                    temporada=temporada,
                    obligatorio=bool(fila.get("obligatorio", True)),
                    fundamento=str(fila.get("fundamento") or ""),
                    origen=contexto.split(" ")[0].upper(),
                )
            )
        return requisitos

    def _cargar_matriz(self) -> None:
        datos = yaml.safe_load(self._ruta_matriz.read_text(encoding="utf-8")) or {}
        self._estado_matriz = str(datos.get("estado") or "DESCONOCIDO")
        self._base = self._leer_requisitos(
            (datos.get("base_operativa") or {}).get("elementos"),
            "BASE operativa",
        )
        for codigo, definicion in (datos.get("sectores") or {}).items():
            self._sectores[str(codigo).strip()] = {
                "nombre": str(definicion.get("nombre") or codigo),
                "aplica_base": bool(definicion.get("aplica_base", True)),
                "elementos": self._leer_requisitos(
                    definicion.get("elementos"),
                    f"SECTOR {codigo}",
                ),
            }
        for codigo, definicion in (datos.get("puestos") or {}).items():
            self._puestos[str(codigo).strip()] = self._leer_requisitos(
                definicion.get("elementos"),
                f"PUESTO {codigo}",
            )

    def obtener_elemento(self, codigo: str) -> ElementoEPP | None:
        return self._elementos.get(str(codigo).strip())

    def listar_elementos(self) -> list[ElementoEPP]:
        return sorted(self._elementos.values(), key=lambda e: _orden_codigo(e.codigo))

    def requisitos_de(self, sector_codigo: str, puesto_codigo: str) -> list[RequisitoEPP]:
        """Compone base + sector + puesto sin repetir ni reducir cantidades."""
        sector = self._sectores.get(str(sector_codigo).strip())
        acumulado: dict[str, RequisitoEPP] = {}

        def sumar(requisitos: list[RequisitoEPP]) -> None:
            for requisito in requisitos:
                previo = acumulado.get(requisito.codigo)
                if (
                    previo is None
                    or PESO[requisito.origen] > PESO[previo.origen]
                    or (
                        PESO[requisito.origen] == PESO[previo.origen]
                        and requisito.cantidad > previo.cantidad
                    )
                ):
                    acumulado[requisito.codigo] = requisito

        if sector is None or sector["aplica_base"]:
            sumar(self._base)
        if sector is not None:
            sumar(sector["elementos"])
        sumar(self._puestos.get(str(puesto_codigo).strip(), []))
        return sorted(
            acumulado.values(),
            key=lambda requisito: (
                not requisito.obligatorio,
                self._elementos[requisito.codigo].familia,
                _orden_codigo(requisito.codigo),
            ),
        )

    def sector_definido(self, sector_codigo: str) -> bool:
        return str(sector_codigo).strip() in self._sectores

    def nombre_sector(self, sector_codigo: str) -> str:
        sector = self._sectores.get(str(sector_codigo).strip())
        return str(sector["nombre"]) if sector else str(sector_codigo)

    def aplica_base(self, sector_codigo: str) -> bool:
        sector = self._sectores.get(str(sector_codigo).strip())
        return bool(sector["aplica_base"]) if sector else True
