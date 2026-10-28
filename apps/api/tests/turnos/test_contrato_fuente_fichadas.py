from datetime import UTC, date, datetime

from suite_juviar.modulos.turnos.domain.entidades import Fichada
from suite_juviar.modulos.turnos.infrastructure.simulados import FuenteFichadasSimulada


def test_contrato_fuente_fichadas_filtra_periodo_y_marca_origen():
    fuente = FuenteFichadasSimulada([
        Fichada("10", datetime(2026, 9, 1, 8, tzinfo=UTC), "ENTRADA"),
        Fichada("10", datetime(2026, 10, 1, 8, tzinfo=UTC), "ENTRADA"),
    ])
    filas = fuente.listar(date(2026, 9, 1), date(2026, 9, 30))
    assert len(filas) == 1
    assert filas[0].legajo == "10"
    assert filas[0].simulada is True
    assert fuente.simulada is True
