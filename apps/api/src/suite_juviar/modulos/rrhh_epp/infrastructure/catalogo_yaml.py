"""Catálogo RD 068/11 y matriz sector + puesto desde YAML.

El catálogo se regenera desde el Excel de RRHH. La matriz usa como base los 19
sectores del esquema de ENAV y agrega requisitos específicos por puesto.

Al cargar valida que la matriz no apunte a códigos inexistentes. Es preferible
que la aplicación no arranque a que un operario vea en pantalla un elemento
que no existe.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import yaml

from ..domain.modelos_mvp import ElementoEPP, ItemCatalogo, RequisitoEPP

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
    def __init__(
        self,
        ruta_catalogo: str | Path,
        ruta_matriz: str | Path,
        ruta_vida_util: str | Path | None = None,
        ruta_items: str | Path | None = None,
    ) -> None:
        self._ruta_catalogo = Path(ruta_catalogo)
        self._ruta_matriz = Path(ruta_matriz)
        self._ruta_vida_util = Path(ruta_vida_util) if ruta_vida_util else None
        self._ruta_items = Path(ruta_items) if ruta_items else None
        self._vida_familia: dict[str, dict] = {}
        self._vida_codigo: dict[str, dict] = {}
        self._elementos: dict[str, ElementoEPP] = {}
        self._items: dict[str, ItemCatalogo] = {}
        self._base: list[RequisitoEPP] = []
        self._sectores: dict[str, dict] = {}
        self._puestos: dict[str, list[RequisitoEPP]] = {}
        self._estado_matriz = "DESCONOCIDO"
        self._version_norma = ""
        self._estado_vida_util = "SIN_TABLA"
        self._estado_items = "SIN_CATALOGO"
        self._dueno_items = "SIN_DEFINIR"
        self._cargar_vida_util()
        self._cargar_catalogo()
        self._cargar_items()
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

    @property
    def estado_vida_util(self) -> str:
        return self._estado_vida_util

    @property
    def estado_items(self) -> str:
        return self._estado_items

    @property
    def dueno_items(self) -> str:
        return self._dueno_items

    @property
    def tiene_items_simulados(self) -> bool:
        return any(
            item.codigo_interno.startswith("SIM-") or item.estado == "SIMULADO"
            for item in self._items.values()
        )

    def _cargar_vida_util(self) -> None:
        if not self._ruta_vida_util or not self._ruta_vida_util.exists():
            return
        datos = yaml.safe_load(self._ruta_vida_util.read_text(encoding="utf-8")) or {}
        self._estado_vida_util = str(datos.get("estado") or "DESCONOCIDO")
        self._vida_familia = datos.get("por_familia") or {}
        self._vida_codigo = datos.get("por_codigo") or {}

    def _vida_util(self, codigo: str, familia: str) -> tuple[int | None, str]:
        if codigo in self._vida_codigo:
            definicion = self._vida_codigo[codigo]
            return definicion.get("dias"), str(definicion.get("criterio") or "")
        if familia in self._vida_familia:
            definicion = self._vida_familia[familia]
            return definicion.get("dias"), str(definicion.get("criterio") or "")
        return None, ""

    def _cargar_catalogo(self) -> None:
        datos = yaml.safe_load(self._ruta_catalogo.read_text(encoding="utf-8")) or {}
        self._version_norma = str(datos.get("version_norma") or "")
        for fila in datos.get("elementos") or []:
            codigo = str(fila["codigo"]).strip()
            if codigo in self._elementos:
                raise ErrorDeCatalogo(f"Código {codigo} duplicado en el catálogo.")
            familia = str(fila.get("familia") or "Otros")
            dias, criterio = self._vida_util(codigo, familia)
            self._elementos[codigo] = ElementoEPP(
                codigo=codigo,
                producto=str(fila["producto"]),
                tipo_modelo=str(fila.get("tipo_modelo") or ""),
                marca=str(fila.get("marca") or ""),
                posee_certificacion=bool(fila.get("posee_certificacion")),
                certificacion=fila.get("certificacion"),
                unidad=str(fila.get("unidad") or "unidad"),
                vida_util_dias=(
                    fila.get("vida_util_dias") if fila.get("vida_util_dias") is not None else dias
                ),
                familia=familia,
                destino_declarado=fila.get("destino_declarado"),
                criterio_vida_util=str(fila.get("criterio_vida_util") or criterio),
            )
        if not self._elementos:
            raise ErrorDeCatalogo(f"{self._ruta_catalogo.name} está vacío.")

    def _cargar_items(self) -> None:
        if not self._ruta_items or not self._ruta_items.exists():
            return
        datos = yaml.safe_load(self._ruta_items.read_text(encoding="utf-8")) or {}
        self._estado_items = str(datos.get("estado") or "DESCONOCIDO")
        self._dueno_items = str(datos.get("dueno_dato") or "SIN_DEFINIR")
        for fila in datos.get("items") or []:
            codigo = str(fila.get("codigo_interno") or "").strip()
            elemento_codigo = str(fila.get("elemento_codigo") or "").strip()
            if not codigo:
                raise ErrorDeCatalogo("Hay un ítem sin código interno.")
            if codigo in self._items:
                raise ErrorDeCatalogo(f"Código interno {codigo} duplicado.")
            if elemento_codigo not in self._elementos:
                raise ErrorDeCatalogo(
                    f"El ítem {codigo} apunta al elemento inexistente {elemento_codigo}."
                )
            self._items[codigo] = ItemCatalogo(
                codigo_interno=codigo,
                elemento_codigo=elemento_codigo,
                marca=str(fila.get("marca") or "SIN_DATO"),
                modelo=str(fila.get("modelo") or "SIN_DATO"),
                talle=str(fila.get("talle") or "SIN_DATO"),
                color=str(fila.get("color") or "SIN_DATO"),
                estado=str(fila.get("estado") or self._estado_items),
            )
        simulados = {
            item.codigo_interno.startswith("SIM-") or item.estado == "SIMULADO"
            for item in self._items.values()
        }
        if len(simulados) > 1:
            raise ErrorDeCatalogo(
                "El catálogo de ítems no admite una fusión de registros reales y SIM-*. "
                "La carga aprobada por Higiene y Seguridad debe reemplazar el archivo completo."
            )

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
                raise ErrorDeCatalogo(f"{contexto}/{codigo}: frecuencia inválida '{frecuencia}'.")
            if temporada not in TEMPORADAS:
                raise ErrorDeCatalogo(f"{contexto}/{codigo}: temporada inválida '{temporada}'.")
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

    def obtener_item(self, codigo_interno: str) -> ItemCatalogo | None:
        return self._items.get(str(codigo_interno).strip())

    def items_de(self, elemento_codigo: str) -> list[ItemCatalogo]:
        return sorted(
            (
                item
                for item in self._items.values()
                if item.elemento_codigo == str(elemento_codigo).strip()
            ),
            key=lambda item: item.codigo_interno,
        )

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

    FAMILIAS_CRITICAS: ClassVar[frozenset[str]] = frozenset(
        {
            "Guantes",
            "Calzado de seguridad",
            "Protección ocular",
            "Protección auditiva",
            "Protección respiratoria",
            "Protección de cráneo",
            "Protección contra caídas",
            "Protección facial",
            "Filtros y cartuchos",
            "Protección para soldadura",
        }
    )
    REFERENCIAS_DEROGADAS: ClassVar[tuple[str, ...]] = (
        "896/99",
        "896/1999",
        "SELLO S",
    )

    def alertas(self) -> list[dict[str, object]]:
        """Auditoría informativa: nunca bloquea una entrega."""
        salida: list[dict[str, object]] = []
        for elemento in self.listar_elementos():
            motivos: list[str] = []
            if not elemento.marca:
                motivos.append("sin marca declarada")
            if not elemento.tipo_modelo:
                motivos.append("sin tipo/modelo declarado")
            if not elemento.posee_certificacion and elemento.familia in self.FAMILIAS_CRITICAS:
                motivos.append(
                    f"sin certificación declarada, y {elemento.familia.lower()} debería tenerla"
                )
            certificacion = (elemento.certificacion or "").upper()
            for comilla in ('"', "'", "\u201c", "\u201d", "\u00ab", "\u00bb"):
                certificacion = certificacion.replace(comilla, "")
            if any(referencia in certificacion for referencia in self.REFERENCIAS_DEROGADAS):
                motivos.append(
                    "cita una referencia derogada por la Res. SIC 18/2025 "
                    "(que eliminó el sello S y reemplazó a la Res. 896/99)"
                )
            if elemento.vida_util_dias is None and elemento.familia != "Protección lumbar":
                motivos.append("sin vida útil definida: el sistema no puede avisar vencimiento")
            if motivos:
                salida.append(
                    {
                        "codigo": elemento.codigo,
                        "producto": elemento.producto,
                        "tipo_modelo": elemento.tipo_modelo,
                        "familia": elemento.familia,
                        "motivos": motivos,
                    }
                )
        return salida
