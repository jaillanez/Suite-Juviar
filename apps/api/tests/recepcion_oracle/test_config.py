import pytest

from suite_juviar.modulos.recepcion.integracion_oracle.config import Config

VARIABLES_ORACLE = {
    "RECEPCION_SEDES_ACTIVAS": "chimbas",
    "RECEPCION_CHIMBAS_HOST": "200.114.96.131",
    "RECEPCION_ORACLE_USUARIO": "usuario_reporte",
    "RECEPCION_ORACLE_CLAVE": "secreto-de-prueba",
}


def test_diagnostico_no_exige_destinos(monkeypatch) -> None:
    for nombre, valor in VARIABLES_ORACLE.items():
        monkeypatch.setenv(nombre, valor)
    monkeypatch.delenv("RECEPCION_DSN_SUITE", raising=False)
    monkeypatch.delenv("RECEPCION_DSN_DMZ", raising=False)

    config = Config.desde_entorno(requerir_destinos=False)

    assert config.sedes[0].host == "200.114.96.131"
    assert config.dsn_suite == ""
    assert config.dsn_dmz == ""


def test_worker_si_exige_destinos(monkeypatch) -> None:
    for nombre, valor in VARIABLES_ORACLE.items():
        monkeypatch.setenv(nombre, valor)
    monkeypatch.delenv("RECEPCION_DSN_SUITE", raising=False)
    monkeypatch.delenv("RECEPCION_DSN_DMZ", raising=False)

    with pytest.raises(RuntimeError, match="SJ_DATABASE_URL"):
        Config.desde_entorno()
