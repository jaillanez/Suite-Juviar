from datetime import UTC, datetime, timedelta

import pytest

from modulos.fila.orden import (
    ESPONTANEO,
    ORGANICO,
    EnEspera,
    SalteoSinMotivo,
    elegir_llamado,
    grupo,
    ordenar,
    posicion,
)

T0 = datetime(2026, 3, 3, 7, 0, tzinfo=UTC)
CERT = frozenset({"20-1"})


def e(id_, cuit="20-9", org=False, turno=False, min_=0):
    return EnEspera(id_, cuit, org, turno, T0 + timedelta(minutes=min_))


def test_organico_certificado_primero():
    assert grupo(e(1, "20-1", org=True), CERT) == ORGANICO


def test_organico_declarado_sin_certificado_no_tiene_prioridad():
    assert grupo(e(1, "20-9", org=True), CERT) == ESPONTANEO


def test_organico_certificado_con_turno_sigue_siendo_organico():
    assert grupo(e(1, "20-1", org=True, turno=True), CERT) == ORGANICO


def test_certificado_que_no_declara_organica_no_tiene_prioridad():
    assert grupo(e(1, "20-1", org=False), CERT) == ESPONTANEO


def test_orden_completo():
    fila = [
        e(1),
        e(2, turno=True, min_=10),
        e(3, "20-1", org=True, min_=20),
        e(4, turno=True, min_=5),
    ]
    assert [x.id for x in ordenar(fila, CERT)] == [3, 4, 2, 1]


def test_dentro_del_grupo_manda_la_confirmacion():
    assert [x.id for x in ordenar([e(1, min_=9), e(2, min_=3)], CERT)] == [2, 1]


def test_llamar_siguiente_no_saltea_a_nadie():
    llamado, salteados = elegir_llamado([e(1), e(2, min_=1)], CERT)
    assert llamado.id == 1 and salteados == []


def test_saltear_sin_motivo_se_rechaza():
    with pytest.raises(SalteoSinMotivo):
        elegir_llamado([e(1), e(2, min_=1)], CERT, elegido_id=2)
    with pytest.raises(SalteoSinMotivo):
        elegir_llamado([e(1), e(2, min_=1)], CERT, elegido_id=2, motivo="porque sí")


def test_saltear_con_motivo_informa_a_quienes():
    llamado, salteados = elegir_llamado(
        [e(1), e(2, min_=1), e(3, min_=2)], CERT, elegido_id=3, motivo="no_responde"
    )
    assert llamado.id == 3 and salteados == [1, 2]


def test_fila_vacia():
    with pytest.raises(LookupError):
        elegir_llamado([], CERT)


def test_posicion():
    fila = [e(1), e(2, turno=True, min_=5)]
    assert posicion(fila, 2, CERT) == 1 and posicion(fila, 1, CERT) == 2
    assert posicion(fila, 99, CERT) is None
