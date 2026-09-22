from datetime import UTC, datetime, timedelta

import pytest

from fila_app.guardias import (
    HORAS_SESION,
    ClaveInvalida,
    Sesion,
    hashear,
    nuevo_token,
    vencimiento,
    verificar,
)

AHORA = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)


def test_la_clave_correcta_entra():
    assert verificar("portonchimbas", hashear("portonchimbas"))


@pytest.mark.parametrize("intento", ["otra-clave", "", " portonchimbas", "PORTONCHIMBAS"])
def test_la_clave_incorrecta_no_entra(intento):
    assert not verificar(intento, hashear("portonchimbas"))


def test_clave_corta():
    with pytest.raises(ClaveInvalida):
        hashear("123")


def test_sesion_actor_vencimiento_y_sede():
    sesion = Sesion("mgomez", "chimbas", vencimiento(AHORA))
    assert sesion.actor == "guardia:mgomez"
    assert sesion.vigente(AHORA + timedelta(hours=HORAS_SESION - 1))
    assert not sesion.vigente(AHORA + timedelta(hours=HORAS_SESION, seconds=1))
    assert sesion.puede_operar("chimbas") and not sesion.puede_operar("lavalle")


def test_tokens_unicos():
    assert len({nuevo_token() for _ in range(500)}) == 500
