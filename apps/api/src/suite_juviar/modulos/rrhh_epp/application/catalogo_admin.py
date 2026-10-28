from __future__ import annotations

import io
import zipfile
from dataclasses import asdict
from datetime import date
from uuid import uuid4
from xml.etree import ElementTree

from ..domain.modelos_mvp import ItemCatalogo

NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
COLUMNAS = ("elemento_codigo", "codigo_interno", "marca", "modelo", "talle", "color")


def leer_items_xlsx(contenido: bytes) -> list[ItemCatalogo]:
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as libro:
            compartidas: list[str] = []
            if "xl/sharedStrings.xml" in libro.namelist():
                raiz = ElementTree.fromstring(libro.read("xl/sharedStrings.xml"))
                compartidas = ["".join(si.itertext()) for si in raiz.findall("x:si", NS)]
            hoja = ElementTree.fromstring(libro.read("xl/worksheets/sheet1.xml"))
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ValueError("El archivo no es un Excel .xlsx válido.") from exc
    filas: list[list[str]] = []
    for fila in hoja.findall(".//x:row", NS):
        valores = []
        for celda in fila.findall("x:c", NS):
            nodo = celda.find("x:v", NS)
            valor = nodo.text if nodo is not None and nodo.text else ""
            if celda.attrib.get("t") == "s" and valor:
                valor = compartidas[int(valor)]
            valores.append(valor.strip())
        filas.append(valores)
    if not filas:
        raise ValueError("El Excel no contiene filas.")
    cabecera = tuple(valor.casefold() for valor in filas[0])
    if cabecera[: len(COLUMNAS)] != COLUMNAS:
        raise ValueError("La primera hoja debe comenzar con: " + ", ".join(COLUMNAS))
    return [
        ItemCatalogo(
            codigo_interno=fila[1], elemento_codigo=fila[0], marca=fila[2],
            modelo=fila[3], talle=fila[4], color=fila[5], estado="IMPORTADO_HYS",
        )
        for fila in filas[1:] if len(fila) >= len(COLUMNAS) and any(fila)
    ]


class ImportacionesCatalogo:
    def __init__(self, catalogo, entregas) -> None:
        self.catalogo = catalogo
        self.entregas = entregas
        self._pendientes: dict[str, list[ItemCatalogo]] = {}

    def previsualizar(self, contenido: bytes) -> dict[str, object]:
        items = leer_items_xlsx(contenido)
        identificador = str(uuid4())
        self._pendientes[identificador] = items
        actuales = {item.codigo_interno: item for item in self.catalogo.listar_items()}
        nuevos = {item.codigo_interno: item for item in items}
        desaparecen = actuales.keys() - nuevos.keys()
        afectadas = [
            entrega for entrega in self.entregas.listar_periodo(date.min, date.max)
            if any(linea.item_codigo in desaparecen for linea in entrega.lineas)
        ]
        return {
            "id": identificador,
            "agrega": sorted(nuevos.keys() - actuales.keys()),
            "cambia": sorted(codigo for codigo in nuevos.keys() & actuales.keys()
                              if asdict(nuevos[codigo]) != asdict(actuales[codigo])),
            "desaparece": sorted(desaparecen),
            "entregas_afectadas": len(afectadas),
            "entregas_afectadas_ids": sorted(entrega.id for entrega in afectadas),
            "total": len(items),
        }

    def aplicar(self, identificador: str) -> dict[str, object]:
        items = self._pendientes.pop(identificador, None)
        if items is None:
            raise LookupError("No existe esa previsualización.")
        self.catalogo.reemplazar_items(items)
        return {"id": identificador, "aplicados": len(items), "modo": "REEMPLAZO"}
