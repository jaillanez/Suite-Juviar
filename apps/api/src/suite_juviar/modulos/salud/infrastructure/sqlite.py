from __future__ import annotations

from pathlib import Path

from suite_juviar.plataforma.persistencia.sqlite_colecciones import (
    BaseColeccionesSQLite,
    ListaSQLite,
    MapaSQLite,
)

from ..domain.modelos import Diagnostico
from .simulados import AdjuntosSaludCifradosMemoria, SaludMemoria


DIAGNOSTICOS_INICIALES = (
    ("RESP", "Enfermedades respiratorias", None),
    ("RESP-IRA", "Infección respiratoria aguda", "RESP"),
    ("RESP-GRIPE", "Gripe", "RESP"),
    ("RESP-NEUM", "Neumonía", "RESP"),
    ("RESP-ASMA", "Asma", "RESP"),
    ("TRAU", "Traumatismos", None),
    ("TRAU-CONT", "Contusión", "TRAU"),
    ("TRAU-ESG", "Esguince", "TRAU"),
    ("TRAU-FRAC", "Fractura", "TRAU"),
    ("TRAU-HER", "Herida", "TRAU"),
    ("MUSC", "Trastornos musculoesqueléticos", None),
    ("MUSC-LUMB", "Lumbalgia", "MUSC"),
    ("MUSC-CERV", "Cervicalgia", "MUSC"),
    ("MUSC-TEND", "Tendinitis", "MUSC"),
    ("DIG", "Enfermedades digestivas", None),
    ("DIG-GAST", "Gastroenteritis", "DIG"),
    ("DIG-GASTR", "Gastritis", "DIG"),
    ("CARD", "Enfermedades cardiovasculares", None),
    ("CARD-HTA", "Hipertensión arterial", "CARD"),
    ("CARD-ARR", "Arritmia", "CARD"),
    ("NEUR", "Enfermedades neurológicas", None),
    ("NEUR-MIG", "Migraña", "NEUR"),
    ("SALUD-MENTAL", "Salud mental", None),
    ("SALUD-MENTAL-ANS", "Trastorno de ansiedad", "SALUD-MENTAL"),
    ("SALUD-MENTAL-DEP", "Trastorno depresivo", "SALUD-MENTAL"),
    ("INF", "Enfermedades infecciosas", None),
    ("INF-COVID", "COVID-19", "INF"),
    ("INF-DENGUE", "Dengue", "INF"),
    ("DERM", "Enfermedades dermatológicas", None),
    ("DERM-DERM", "Dermatitis", "DERM"),
    ("OFT", "Enfermedades oftalmológicas", None),
    ("OFT-CONJ", "Conjuntivitis", "OFT"),
    ("OBST", "Embarazo y puerperio", None),
    ("OBST-COMP", "Complicaciones del embarazo", "OBST"),
    ("OTRO", "Otros diagnósticos", None),
    ("OTRO-REPOSO", "Reposo indicado por profesional", "OTRO"),
)


class CatalogoDiagnosticoSQLite:
    simulada = False
    dueno_dato = "Servicio Médico"

    def __init__(self, ruta: str | Path) -> None:
        self._items = MapaSQLite(BaseColeccionesSQLite(ruta), "salud.diagnosticos")
        if not len(self._items):
            for codigo, descripcion, padre in DIAGNOSTICOS_INICIALES:
                self.guardar(Diagnostico(codigo, descripcion, padre))

    def obtener(self, codigo: str) -> Diagnostico | None:
        return self._items.get(codigo)

    def listar(self) -> list[Diagnostico]:
        return sorted(self._items.values(), key=lambda item: (item.padre_codigo or "", item.descripcion))

    def guardar(self, diagnostico: Diagnostico) -> None:
        self._items[diagnostico.codigo] = diagnostico

    def eliminar(self, codigo: str) -> None:
        if any(item.padre_codigo == codigo for item in self._items.values()):
            raise ValueError("No se puede eliminar una categoría que todavía tiene diagnósticos.")
        try:
            del self._items[codigo]
        except KeyError as exc:
            raise LookupError("Diagnóstico inexistente.") from exc


class SaludSQLite(SaludMemoria):
    def __init__(self, ruta: str | Path) -> None:
        base = BaseColeccionesSQLite(ruta)
        self.certificados = MapaSQLite(base, "salud.certificados")
        self.consultas = ListaSQLite(base, "salud.auditoria")


class AdjuntosSaludCifradosSQLite(AdjuntosSaludCifradosMemoria):
    def __init__(self, clave: bytes, ruta: str | Path) -> None:
        super().__init__(clave)
        self._filas = MapaSQLite(BaseColeccionesSQLite(ruta), "salud.adjuntos")
