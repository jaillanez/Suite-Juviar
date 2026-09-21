from datetime import UTC, datetime
from decimal import Decimal

import pytest

from suite_juviar.modulos.recepcion.integracion_aynux.modelo import (
    DESCARGADO,
    EN_DESCARGA,
    FilaInvalida,
    FilaOrigen,
    huella,
)


def _crudo(**extra) -> dict:
    base = {
        "ID": "0000000476",
        "CIU": 9213965,
        "FECHA": datetime(2026, 3, 3, 12, 58, tzinfo=UTC),
        "NETO": 11560,
        "NROINSCRIPTO": "J80123  ",
        "AZUCAR": Decimal(217),
    }
    base.update(extra)
    return base


def test_ciu_es_la_clave_y_se_normaliza_a_texto() -> None:
    fila = FilaOrigen.desde_oracle("chimbas", _crudo())
    assert fila.ciu == "9213965"
    assert fila.valores["id_origen"] == "0000000476"


def test_recorta_relleno_de_oracle() -> None:
    assert FilaOrigen.desde_oracle("chimbas", _crudo()).valores["nroinscripto"] == "J80123"


def test_cadena_en_blanco_es_nula() -> None:
    fila = FilaOrigen.desde_oracle("chimbas", _crudo(OBSERVACION="   "))
    assert fila.valores["observacion"] is None


def test_sin_ciu_se_rechaza() -> None:
    with pytest.raises(FilaInvalida):
        FilaOrigen.desde_oracle("chimbas", _crudo(CIU=None))


def test_fecha_nula_es_camion_en_descarga() -> None:
    assert FilaOrigen.desde_oracle("chimbas", _crudo(FECHA=None, NETO=None)).estado == EN_DESCARGA
    assert FilaOrigen.desde_oracle("chimbas", _crudo()).estado == DESCARGADO


def test_huella_estable_entre_tipos_numericos_equivalentes() -> None:
    assert huella({"azucar": Decimal("217.0")}) == huella({"azucar": 217})


def test_huella_cambia_si_cambia_el_peso() -> None:
    antes = FilaOrigen.desde_oracle("chimbas", _crudo())
    despues = FilaOrigen.desde_oracle("chimbas", _crudo(NETO=11600))
    assert antes.huella != despues.huella
