from datetime import UTC, datetime, timedelta

import pytest

from plataforma.terceros import permisos as P
from plataforma.terceros.invitacion import (
    MAX_INTENTOS,
    VIGENCIA,
    Invitacion,
    Rechazo,
    generar_codigo,
    hash_codigo,
    validar_intento,
)

ADMIN = frozenset(P.TAREAS)
VER = frozenset({P.VER_INFORMES})
PIM = "pimienta-del-servidor"
T0 = datetime(2026, 9, 22, 9, 0, tzinfo=UTC)
TEL = "5492645000001"


def _inv(codigo="123456", intentos=0, estado="pendiente", creada=T0):
    return Invitacion("20-1", TEL, hash_codigo(codigo, PIM), creada, intentos, estado)


def test_importados_son_administradores_invitados_no():
    assert P.ADMINISTRAR_CONTACTOS in P.POR_DEFECTO_IMPORTADO
    assert P.ADMINISTRAR_CONTACTOS not in P.POR_DEFECTO_INVITADO


def test_no_se_elimina_el_ultimo_administrador():
    with pytest.raises(P.PermisoInvalido):
        P.validar_cambio({"a": ADMIN, "b": VER}, "a", None)


def test_no_se_degrada_el_ultimo_administrador():
    with pytest.raises(P.PermisoInvalido):
        P.validar_cambio({"a": ADMIN}, "a", VER)


def test_control_negativo_con_dos_administradores_si_se_puede():
    P.validar_cambio({"a": ADMIN, "b": ADMIN}, "a", None)


def test_tareas_vacias_o_inventadas():
    with pytest.raises(P.PermisoInvalido):
        P.validar_tareas(set())
    with pytest.raises(P.PermisoInvalido):
        P.validar_tareas({"ver_informes", "ser_dios"})


def test_codigo_correcto_desde_el_numero_invitado():
    assert validar_intento(_inv(), TEL, "123456", PIM, T0 + timedelta(minutes=5)) == "consumida"


def test_codigo_correcto_desde_otro_numero_se_rechaza():
    with pytest.raises(Rechazo):
        validar_intento(_inv(), "5492645999999", "123456", PIM, T0)


def test_codigo_incorrecto_suma_intento():
    assert validar_intento(_inv(), TEL, "000000", PIM, T0) == "pendiente"


def test_tercer_fallo_anula():
    assert validar_intento(_inv(intentos=MAX_INTENTOS - 1), TEL, "000000", PIM, T0) == "anulada"


def test_vencida():
    with pytest.raises(Rechazo):
        validar_intento(_inv(), TEL, "123456", PIM, T0 + VIGENCIA + timedelta(seconds=1))


@pytest.mark.parametrize("estado", ["consumida", "anulada", "vencida"])
def test_no_se_reutiliza(estado):
    with pytest.raises(Rechazo):
        validar_intento(_inv(estado=estado), TEL, "123456", PIM, T0)


def test_hash_depende_de_la_pimienta():
    assert hash_codigo("123456", "a") != hash_codigo("123456", "b")


def test_codigo_seis_digitos():
    assert all(len(c) == 6 and c.isdigit() for c in (generar_codigo() for _ in range(200)))
