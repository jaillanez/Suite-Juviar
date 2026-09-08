from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from suite_juviar.modulos.turnos.api.app import crear_app
from suite_juviar.modulos.turnos.application.servicios import ConciliarTurnos
from suite_juviar.modulos.turnos.domain.entidades import (
    EstadoImputacion,
    Fichada,
    FuenteSimuladaEnProduccion,
)
from suite_juviar.modulos.turnos.infrastructure.simulados import (
    ExportadorArchivoSimulado,
    FuenteFichadasSimulada,
)


def servicio(tmp_path):
    fuente = FuenteFichadasSimulada([
        Fichada("10", datetime(2026, 9, 1, 8, tzinfo=UTC), "ENTRADA"),
        Fichada("10", datetime(2026, 9, 1, 15, tzinfo=UTC), "SALIDA"),
    ])
    return ConciliarTurnos(fuente, ExportadorArchivoSimulado(tmp_path))


def test_cronograma_auditable_concilia_y_no_imputa_solo(tmp_path):
    s = servicio(tmp_path)
    plan = s.cargar_cronograma("10", "BOD", date(2026, 9, 1), time(8), time(16), "supervisor-1")
    propuestas = s.conciliar(date(2026, 9, 1), date(2026, 9, 1))
    assert plan.autor == "supervisor-1"
    assert propuestas[0].estado is EstadoImputacion.PROPUESTA
    ruta = s.aprobar_lote([str(propuestas[0].id)], "rrhh-1")
    assert propuestas[0].estado is EstadoImputacion.APROBADA
    assert "DATOS SIMULADOS — SIN VALIDEZ" in Path(ruta).read_text(encoding="utf-8")


def test_pantalla_marcada_y_produccion_rechaza_simulados(tmp_path):
    s = servicio(tmp_path)
    assert "DATOS SIMULADOS — SIN VALIDEZ" in TestClient(
        crear_app(s), headers={"X-Perfil-Simulado": "RRHH"}
    ).get("/").text
    with pytest.raises(FuenteSimuladaEnProduccion):
        crear_app(s, "produccion")


def test_certificado_propone_enfermedad_pero_no_la_aprueba(tmp_path):
    s = ConciliarTurnos(
        FuenteFichadasSimulada(
            [Fichada("10", datetime(2026, 9, 2, 8, tzinfo=UTC), "CERTIFICADO_MEDICO")]
        ),
        ExportadorArchivoSimulado(tmp_path),
    )
    s.cargar_cronograma("10", "BOD", date(2026, 9, 2), time(8), time(16), "sup-1")
    propuesta = s.conciliar(date(2026, 9, 2), date(2026, 9, 2))[0]
    assert propuesta.motivo_propuesto == "ENFERMEDAD"
    assert propuesta.estado is EstadoImputacion.PROPUESTA
