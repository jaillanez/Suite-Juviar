from __future__ import annotations

import io
import zipfile
from uuid import UUID, uuid4, uuid5
from xml.etree import ElementTree

from ..domain.modelos import Asistencia, Dictado, Participante, Tema

NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
COLUMNAS = (
    "tema",
    "horas",
    "fecha",
    "instructor",
    "duracion_horas",
    "convocatoria_tipo",
    "convocatoria_detalle",
    "convocados",
    "legajo",
    "nombre",
    "presente",
    "supervisor",
)
ESPACIO = UUID("1578e5e0-25c9-4666-9b98-c52d412228c0")


def leer_filas_xlsx(contenido: bytes) -> list[dict[str, str]]:
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
        valores: list[str] = []
        for celda in fila.findall("x:c", NS):
            valor = (
                "".join(celda.itertext()).strip() if celda.attrib.get("t") == "inlineStr" else ""
            )
            nodo = celda.find("x:v", NS)
            if nodo is not None and nodo.text:
                valor = compartidas[int(nodo.text)] if celda.attrib.get("t") == "s" else nodo.text
            valores.append(valor.strip())
        filas.append(valores)
    if not filas or tuple(x.casefold() for x in filas[0][: len(COLUMNAS)]) != COLUMNAS:
        raise ValueError("La primera hoja debe comenzar con: " + ", ".join(COLUMNAS))
    return [dict(zip(COLUMNAS, fila, strict=False)) for fila in filas[1:] if any(fila)]


class ImportacionesHistoricas:
    def __init__(self, repositorio) -> None:
        self.repo = repositorio
        self.pendientes: dict[str, list[dict[str, str]]] = {}

    @staticmethod
    def _clave(fila: dict[str, str]) -> str:
        return f"{fila.get('tema')}|{fila.get('fecha')}|{fila.get('legajo')}"

    def previsualizar(self, contenido: bytes) -> dict[str, object]:
        filas = leer_filas_xlsx(contenido)
        identificador = str(uuid4())
        self.pendientes[identificador] = filas
        actuales = {
            f"{self.repo.obtener_tema(self.repo.obtener_dictado(a.dictado_id).tema_id).nombre}|"
            f"{self.repo.obtener_dictado(a.dictado_id).fecha.isoformat()}|{a.participante.legajo}"
            for a in self.repo.todas_las_asistencias()
        }
        nuevas = {self._clave(f) for f in filas}
        return {
            "id": identificador,
            "agrega": sorted(nuevas - actuales),
            "cambia": sorted(nuevas & actuales),
            "desaparece": sorted(actuales - nuevas),
            "total": len(filas),
            "aclaracion": "Las desapariciones se conservan; el histórico nunca se borra.",
        }

    def aplicar(self, identificador: str) -> dict[str, object]:
        from datetime import date

        filas = self.pendientes.pop(identificador, None)
        if filas is None:
            raise LookupError("No existe esa previsualización.")
        por_tema: dict[str, Tema] = {t.nombre: t for t in self.repo.temas.values()}
        for f in filas:
            tema = por_tema.get(f["tema"])
            if tema is None:
                tema = Tema(str(uuid5(ESPACIO, f"tema:{f['tema']}")), f["tema"], float(f["horas"]))
                self.repo.guardar_tema(tema)
                por_tema[tema.nombre] = tema
            dictado_id = str(uuid5(ESPACIO, f"dictado:{tema.id}:{f['fecha']}:{f['instructor']}"))
            if self.repo.obtener_dictado(dictado_id) is None:
                convocados = tuple(
                    x.strip() for x in f.get("convocados", "").split(",") if x.strip()
                )
                self.repo.guardar_dictado(
                    Dictado(
                        dictado_id,
                        tema.id,
                        date.fromisoformat(f["fecha"]),
                        f["instructor"],
                        float(f["duracion_horas"]),
                        f.get("convocatoria_tipo") or None,
                        f.get("convocatoria_detalle") or None,
                        convocados,
                    )
                )
            self.repo.guardar_asistencia(
                Asistencia(
                    dictado_id,
                    Participante(
                        f["legajo"],
                        f["nombre"],
                        f.get("supervisor", "").casefold() in {"1", "si", "true"},
                    ),
                    f.get("presente", "").casefold() in {"1", "si", "true"},
                    None,
                    "HISTORICO_IMPORTADO",
                )
            )
        return {"id": identificador, "aplicados": len(filas), "desapariciones_borradas": 0}
