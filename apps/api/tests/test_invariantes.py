"""Las reglas que no se pueden violar, verificadas.

No son tests de lógica de negocio: son tests de que la estructura sigue siendo
la que se acordó. Si alguien agrega un setter de peso o un método `guardar` al
repositorio de legajos, estos tests se caen.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from suite_juviar.modulos.recepcion.domain.entidades import OrigenPeso, Pesada, Romaneo
from suite_juviar.plataforma.identidad.domain.puertos import RepositorioLegajos


def _pesada(kg: str) -> Pesada:
    return Pesada(Decimal(kg), OrigenPeso.BASCULA_DIGITAL, datetime.now(UTC), "0001")


def _romaneo() -> Romaneo:
    return Romaneo(
        numero=1,
        productor_cuit="30-69313567-9",
        transportista_cuit="30-11111111-1",
        chofer_dni="20111222",
        patente_chasis="AB123CD",
        variedad="Malbec",
        finca="San José",
        bruto=_pesada("28000"),
    )


def test_el_repositorio_de_legajos_no_permite_escribir():
    """§3.1: Nexus es el dueño del dato. No hay forma de expresar una escritura."""
    metodos = set(dir(RepositorioLegajos))
    assert not {"guardar", "crear", "actualizar", "eliminar"} & metodos


def test_la_pesada_es_inmutable():
    p = _pesada("28000")
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.kg = Decimal(1)  # type: ignore[misc]


def test_corregir_un_romaneo_no_lo_edita():
    original = _romaneo()
    original.cerrar(_pesada("9000"))
    correccion = original.contra_romaneo(2, "tara mal tomada")

    assert original.estado.value == "ANULADO"
    assert original.neto_kg == Decimal(19000)   # el hecho original queda intacto
    assert correccion.anula_a == original.id


def test_recepcion_no_conoce_dinero():
    campos = {f.name for f in dataclasses.fields(Romaneo)}
    prohibidos = {"precio", "importe", "liquidacion", "saldo", "deuda", "tarifa"}
    assert not campos & prohibidos


def test_recepcion_no_conoce_legajos_de_terceros():
    campos = {f.name for f in dataclasses.fields(Romaneo)}
    assert "legajo" not in campos and "productor_legajo" not in campos
