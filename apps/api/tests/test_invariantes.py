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

from suite_juviar.modulos.comercial.ingesta import IngestaSolicitudes
from suite_juviar.modulos.recepcion.domain.entidades import OrigenPeso, Pesada, Romaneo
from suite_juviar.plataforma.identidad.domain.puertos import RepositorioLegajos
from suite_juviar.plataforma.terceros.domain.entidades import Tercero, TipoTercero


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


def test_comprador_exterior_puede_ingresar_sin_identificacion_fiscal():
    comprador = Tercero(
        cuit=None,
        razon_social="Importador GmbH",
        tipo=TipoTercero.COMPRADOR_EXTERIOR,
        pais="DE",
        email="compras@example.de",
    )

    assert comprador.clave_registro == ("EMAIL", "compras@example.de")


def test_identificacion_fiscal_reemplaza_email_como_clave_del_comprador():
    comprador = Tercero(
        cuit=None,
        razon_social="Importador GmbH",
        tipo=TipoTercero.COMPRADOR_EXTERIOR,
        pais="de",
        identificacion_fiscal=" de-12345 ",
        email="compras@example.de",
    )

    assert comprador.clave_registro == ("DE", "DE-12345")


@pytest.mark.parametrize(
    ("linea", "certificaciones", "planta", "sitio"),
    [
        ("bulk_wine", [], "JUVIAR", "Lavalle"),
        ("jcu_decolourised", [], "JUVIAR", "Planta concentradora Lavalle"),
        ("jcu_standard", ["Organic_Letis"], "ENAV", "Chimbas"),
        ("jcu_standard", [], "ENAV", "Media Agua"),
        ("jcu_virgin", [], None, None),
    ],
)
def test_enrutamiento_comercial_se_recalcula_en_el_servidor(
    linea: str,
    certificaciones: list[str],
    planta: str | None,
    sitio: str | None,
):
    carga = {"product_line": linea, "certifications_required": certificaciones}

    assert IngestaSolicitudes._enrutar(carga) == {"planta": planta, "sitio": sitio}
