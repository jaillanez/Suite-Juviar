import pytest

from modulos.fila import cupo, estados
from modulos.fila.patente import PatenteInvalida, normalizar


def test_reserva_dentro_del_cupo():
    cupo.validar(cupo.Reserva(3, 11_000), 1_200_000, 1_100_000)


def test_reserva_excede_informa_lo_disponible():
    with pytest.raises(cupo.SinCupo) as error:
        cupo.validar(cupo.Reserva(3, 11_000), 1_200_000, 1_180_000)
    assert error.value.disponibles == 20_000


def test_control_negativo_justo_en_el_limite_entra():
    cupo.validar(cupo.Reserva(2, 10_000), 1_200_000, 1_180_000)


def test_cupo_sobregirado_no_da_negativo():
    with pytest.raises(cupo.SinCupo) as error:
        cupo.validar(cupo.Reserva(1, 5_000), 100, 200)
    assert error.value.disponibles == 0


@pytest.mark.parametrize(
    "reserva",
    [cupo.Reserva(0, 11_000), cupo.Reserva(51, 11_000), cupo.Reserva(1, 500), cupo.Reserva(1, 90_000)],
)
def test_valores_absurdos(reserva):
    with pytest.raises(ValueError):
        cupo.validar(reserva, 10**9, 0)


def test_estimado():
    assert cupo.estimado_por_camion([9_840, 8_960, 11_680, None, 0]) == 10_200
    assert cupo.estimado_por_camion([]) == cupo.POR_DEFECTO_KG


def test_transiciones():
    estados.validar("pendiente", "en_espera")
    estados.validar("llamado", "en_espera")
    for desde, hacia in [
        ("pendiente", "llamado"),
        ("en_espera", "descargado"),
        ("descargado", "en_espera"),
        ("cancelado", "en_espera"),
    ]:
        with pytest.raises(estados.TransicionInvalida):
            estados.validar(desde, hacia)


@pytest.mark.parametrize(
    ("entrada", "salida"),
    [("ab 123 cd", "AB123CD"), ("abc-123", "ABC123"), (" Aa123bB ", "AA123BB")],
)
def test_patente_valida(entrada, salida):
    assert normalizar(entrada) == salida


@pytest.mark.parametrize("patente", ["", None, "12345", "ABCD123", "AB12CD", "A1B2C3"])
def test_patente_invalida(patente):
    with pytest.raises(PatenteInvalida):
        normalizar(patente)
