from datetime import UTC, datetime

import pytest

from suite_juviar.modulos.recepcion.integracion_oracle.modelo import (
    AUSENTE,
    DESCARGADO,
    EN_DESCARGA,
    INCOMPLETO,
    ClaveDescarga,
    FilaOrigen,
)
from suite_juviar.modulos.recepcion.integracion_oracle.planificador import (
    ClaveDuplicada,
    EstadoLocal,
    planificar,
)


def _fila(
    ciu: str,
    id_origen: str | None = None,
    neto: int | None = 10000,
    fecha: datetime | None = datetime(2026, 3, 1, tzinfo=UTC),
) -> FilaOrigen:
    return FilaOrigen.desde_oracle(
        "chimbas",
        {"CIU": ciu, "ID": id_origen or f"ID-{ciu}", "FECHA": fecha, "NETO": neto},
    )


def _local(fila: FilaOrigen, estado: str | None = None) -> EstadoLocal:
    return EstadoLocal(fila.ciu, fila.clave.id_origen, fila.huella, estado or fila.estado)


def _plan(filas, locales, minimo=1, tope=0.5):
    return planificar(filas, locales, minimo_filas=minimo, tope_ausencias=tope)


def test_fila_desconocida_es_nueva() -> None:
    assert [fila.clave for fila in _plan([_fila("1")], {}).nuevos] == [
        ClaveDescarga("1", "ID-1")
    ]


def test_fila_igual_no_se_toca() -> None:
    fila = _fila("1")
    plan = _plan([fila], {fila.clave: _local(fila)})
    assert plan.sin_cambio == [fila.clave] and not plan.modificados


def test_peso_corregido_en_origen_se_detecta() -> None:
    antes = _fila("1", neto=10000)
    plan = _plan([_fila("1", neto=10200)], {antes.clave: _local(antes)})
    assert [fila.ciu for fila in plan.modificados] == ["1"]


def test_camion_que_termina_de_descargar_se_detecta() -> None:
    antes = _fila("1", neto=None, fecha=None)
    assert _local(antes).estado == EN_DESCARGA
    plan = _plan([_fila("1")], {antes.clave: _local(antes)})
    assert plan.modificados[0].estado == DESCARGADO


def test_fila_que_desaparece_del_origen_queda_ausente() -> None:
    primera, segunda = _fila("1"), _fila("2")
    plan = _plan(
        [primera], {primera.clave: _local(primera), segunda.clave: _local(segunda)}
    )
    assert plan.ausentes == [segunda.clave]


def test_fila_ausente_que_reaparece_se_reactiva() -> None:
    fila = _fila("1")
    plan = _plan([fila], {fila.clave: _local(fila, estado=AUSENTE)})
    assert [item.ciu for item in plan.modificados] == ["1"]


def test_ausente_no_se_vuelve_a_marcar() -> None:
    primera, segunda = _fila("1"), _fila("2")
    plan = _plan(
        [primera],
        {primera.clave: _local(primera), segunda.clave: _local(segunda, estado=AUSENTE)},
    )
    assert plan.ausentes == []


def test_ciu_repetido_frena_todo() -> None:
    with pytest.raises(ClaveDuplicada):
        _plan([_fila("1"), _fila("1", neto=5)], {})


def test_mismo_ciu_con_id_distinto_son_dos_movimientos() -> None:
    plan = _plan([_fila("1", "A"), _fila("1", "B")], {})
    assert [fila.clave for fila in plan.nuevos] == [
        ClaveDescarga("1", "A"),
        ClaveDescarga("1", "B"),
    ]


def test_incompleto_historico_no_se_reactiva_como_camion_actual() -> None:
    fila = _fila("1", neto=None, fecha=None).como_incompleta()
    plan = _plan([_fila("1", neto=None, fecha=None)], {fila.clave: _local(fila)})
    assert plan.sin_cambio == [fila.clave]
    assert _local(fila).estado == INCOMPLETO


def test_lectura_vacia_no_da_de_baja_nada() -> None:
    fila = _fila("1")
    plan = _plan([], {fila.clave: _local(fila)}, minimo=1)
    assert plan.ausentes == [] and plan.ausencias_suspendidas


def test_lectura_parcial_supera_el_tope_y_se_suspende() -> None:
    locales = {_fila(str(i)).clave: _local(_fila(str(i))) for i in range(10)}
    plan = _plan([_fila("0"), _fila("1")], locales, tope=0.2)
    assert plan.ausentes == [] and "tope" in plan.ausencias_suspendidas


def test_control_negativo_bajo_el_tope_si_marca() -> None:
    locales = {_fila(str(i)).clave: _local(_fila(str(i))) for i in range(10)}
    plan = _plan([_fila(str(i)) for i in range(9)], locales, tope=0.2)
    assert plan.ausentes == [ClaveDescarga("9", "ID-9")]
    assert plan.ausencias_suspendidas is None
