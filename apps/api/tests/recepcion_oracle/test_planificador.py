from datetime import UTC, datetime

import pytest

from suite_juviar.modulos.recepcion.integracion_oracle.modelo import (
    AUSENTE,
    DESCARGADO,
    EN_DESCARGA,
    FilaOrigen,
)
from suite_juviar.modulos.recepcion.integracion_oracle.planificador import (
    ClaveDuplicada,
    EstadoLocal,
    planificar,
)


def _fila(
    ciu: str,
    neto: int | None = 10000,
    fecha: datetime | None = datetime(2026, 3, 1, tzinfo=UTC),
) -> FilaOrigen:
    return FilaOrigen.desde_oracle("chimbas", {"CIU": ciu, "FECHA": fecha, "NETO": neto})


def _local(fila: FilaOrigen, estado: str | None = None) -> EstadoLocal:
    return EstadoLocal(fila.ciu, fila.huella, estado or fila.estado)


def _plan(filas, locales, minimo=1, tope=0.5):
    return planificar(filas, locales, minimo_filas=minimo, tope_ausencias=tope)


def test_fila_desconocida_es_nueva() -> None:
    assert [fila.ciu for fila in _plan([_fila("1")], {}).nuevos] == ["1"]


def test_fila_igual_no_se_toca() -> None:
    fila = _fila("1")
    plan = _plan([fila], {"1": _local(fila)})
    assert plan.sin_cambio == ["1"] and not plan.modificados


def test_peso_corregido_en_origen_se_detecta() -> None:
    antes = _fila("1", neto=10000)
    plan = _plan([_fila("1", neto=10200)], {"1": _local(antes)})
    assert [fila.ciu for fila in plan.modificados] == ["1"]


def test_camion_que_termina_de_descargar_se_detecta() -> None:
    antes = _fila("1", neto=None, fecha=None)
    assert _local(antes).estado == EN_DESCARGA
    plan = _plan([_fila("1")], {"1": _local(antes)})
    assert plan.modificados[0].estado == DESCARGADO


def test_fila_que_desaparece_del_origen_queda_ausente() -> None:
    primera, segunda = _fila("1"), _fila("2")
    plan = _plan([primera], {"1": _local(primera), "2": _local(segunda)})
    assert plan.ausentes == ["2"]


def test_fila_ausente_que_reaparece_se_reactiva() -> None:
    fila = _fila("1")
    plan = _plan([fila], {"1": _local(fila, estado=AUSENTE)})
    assert [item.ciu for item in plan.modificados] == ["1"]


def test_ausente_no_se_vuelve_a_marcar() -> None:
    primera, segunda = _fila("1"), _fila("2")
    plan = _plan([primera], {"1": _local(primera), "2": _local(segunda, estado=AUSENTE)})
    assert plan.ausentes == []


def test_ciu_repetido_frena_todo() -> None:
    with pytest.raises(ClaveDuplicada):
        _plan([_fila("1"), _fila("1", neto=5)], {})


def test_lectura_vacia_no_da_de_baja_nada() -> None:
    fila = _fila("1")
    plan = _plan([], {"1": _local(fila)}, minimo=1)
    assert plan.ausentes == [] and plan.ausencias_suspendidas


def test_lectura_parcial_supera_el_tope_y_se_suspende() -> None:
    locales = {str(i): _local(_fila(str(i))) for i in range(10)}
    plan = _plan([_fila("0"), _fila("1")], locales, tope=0.2)
    assert plan.ausentes == [] and "tope" in plan.ausencias_suspendidas


def test_control_negativo_bajo_el_tope_si_marca() -> None:
    locales = {str(i): _local(_fila(str(i))) for i in range(10)}
    plan = _plan([_fila(str(i)) for i in range(9)], locales, tope=0.2)
    assert plan.ausentes == ["9"] and plan.ausencias_suspendidas is None
