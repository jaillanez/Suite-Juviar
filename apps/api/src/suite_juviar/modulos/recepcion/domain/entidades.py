"""Descarga de camiones: pesaje, romaneo, productor, transportista.

Reglas hechas imposibles de violar por construcción:

* `Pesada` es frozen y `Romaneo` no expone setters de peso. Una corrección no
  edita el romaneo original: emite un contra-romaneo que lo referencia. El
  registro de báscula es un hecho, no un campo editable.
* El romaneo referencia al productor por CUIT y al chofer por DNI, nunca por
  legajo. La separación entre personas internas y terceros (§3.2) queda en el
  tipo: no hay dónde poner un legajo acá.
* `Romaneo` no tiene campos de precio, liquidación ni deuda. La recepción
  registra qué entró; lo que se le paga a quién no es asunto de este módulo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4


class OrigenPeso(StrEnum):
    BASCULA_DIGITAL = "BASCULA_DIGITAL"
    CARGA_MANUAL = "CARGA_MANUAL"   # habilitado por parametría, deja bitácora


class EstadoRomaneo(StrEnum):
    ABIERTO = "ABIERTO"        # entró el camión, falta la tara
    CERRADO = "CERRADO"        # peso neto determinado
    ANULADO = "ANULADO"        # reemplazado por un contra-romaneo


@dataclass(frozen=True, slots=True)
class Pesada:
    kg: Decimal
    origen: OrigenPeso
    registrada_en: datetime
    operador_legajo: str

    def __post_init__(self) -> None:
        if self.kg <= 0:
            raise ValueError("La pesada debe ser mayor a cero")


@dataclass(slots=True)
class Romaneo:
    numero: int
    productor_cuit: str
    transportista_cuit: str
    chofer_dni: str
    patente_chasis: str
    variedad: str                     # del maestro de variedades, no texto libre
    finca: str | None
    bruto: Pesada
    id: UUID = field(default_factory=uuid4)
    patente_acoplado: str | None = None
    tara: Pesada | None = None
    estado: EstadoRomaneo = EstadoRomaneo.ABIERTO
    anula_a: UUID | None = None
    abierto_en: datetime = field(default_factory=lambda: datetime.now(UTC))
    cerrado_en: datetime | None = None

    @property
    def neto_kg(self) -> Decimal | None:
        if self.tara is None:
            return None
        return self.bruto.kg - self.tara.kg

    def cerrar(self, tara: Pesada) -> None:
        if self.estado is not EstadoRomaneo.ABIERTO:
            raise ValueError("Solo se cierra un romaneo abierto")
        if tara.kg >= self.bruto.kg:
            raise ValueError("La tara no puede ser mayor o igual al bruto")
        self.tara = tara
        self.estado = EstadoRomaneo.CERRADO
        self.cerrado_en = datetime.now(UTC)

    def contra_romaneo(self, numero_nuevo: int, motivo: str) -> Romaneo:
        """La única forma de corregir. El original queda como fue."""
        if self.estado is EstadoRomaneo.ANULADO:
            raise ValueError("El romaneo ya está anulado")
        self.estado = EstadoRomaneo.ANULADO
        return Romaneo(
            numero=numero_nuevo,
            productor_cuit=self.productor_cuit,
            transportista_cuit=self.transportista_cuit,
            chofer_dni=self.chofer_dni,
            patente_chasis=self.patente_chasis,
            patente_acoplado=self.patente_acoplado,
            variedad=self.variedad,
            finca=self.finca,
            bruto=self.bruto,
            anula_a=self.id,
        )
