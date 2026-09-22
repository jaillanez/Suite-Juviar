from datetime import UTC, datetime, timedelta

import pytest
from fila_app.repositorio import (
    SAN_JUAN,
    RepositorioFila,
    _fecha_operativa,
    _validar_momento,
)


def test_noche_de_san_juan_no_pasa_al_dia_utc_siguiente():
    momento_utc = datetime(2026, 3, 11, 1, 30, tzinfo=UTC)
    assert momento_utc.astimezone(SAN_JUAN).hour == 22
    assert _fecha_operativa(momento_utc).isoformat() == "2026-03-10"


@pytest.mark.parametrize(
    "momento",
    [
        datetime.now(UTC) + timedelta(minutes=3),
        datetime.now(UTC) - timedelta(hours=12, seconds=1),
    ],
)
def test_hora_de_tablet_fuera_de_rango_se_rechaza(momento):
    with pytest.raises(ValueError, match="hora de la tablet"):
        _validar_momento(momento)


@pytest.mark.parametrize("desplazamiento", [-1, 61])
def test_turnos_fuera_de_ventana_se_rechazan_antes_de_ir_a_la_base(desplazamiento):
    fecha = datetime.now(SAN_JUAN).date() + timedelta(days=desplazamiento)
    with pytest.raises(ValueError, match="60 días"):
        RepositorioFila("sin-conexion").reservar_turno(
            {
                "fecha": fecha.isoformat(),
                "camiones": 1,
                "kg_por_camion": 10000,
            }
        )
