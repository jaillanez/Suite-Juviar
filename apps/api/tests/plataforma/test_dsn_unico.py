import pytest

from suite_juviar.plataforma.db import dsn


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    for variable in (dsn.VARIABLE, *dsn.HEREDADAS):
        monkeypatch.delenv(variable, raising=False)


def test_convierte_entre_psycopg_y_sqlalchemy(monkeypatch):
    monkeypatch.setenv(dsn.VARIABLE, "postgresql://sj_app@localhost/suite")
    assert dsn.dsn_psycopg() == "postgresql://sj_app@localhost/suite"
    assert dsn.url_sqlalchemy() == "postgresql+asyncpg://sj_app@localhost/suite"


@pytest.mark.parametrize("heredada", dsn.HEREDADAS)
def test_variable_heredada_funciona_y_avisa(monkeypatch, heredada):
    monkeypatch.setenv(heredada, "postgresql://sj_app@localhost/suite")
    with pytest.warns(DeprecationWarning, match=heredada):
        assert dsn.dsn_psycopg().endswith("/suite")


def test_sin_variable_no_inventa_una_base():
    assert dsn.dsn_psycopg(obligatorio=False) == ""
    with pytest.raises(dsn.FaltaLaBaseDeDatos, match=dsn.VARIABLE):
        dsn.dsn_psycopg()


def test_rechaza_una_conexion_que_no_es_postgresql(monkeypatch):
    monkeypatch.setenv(dsn.VARIABLE, "mysql://localhost/suite")
    with pytest.raises(dsn.FaltaLaBaseDeDatos, match="postgresql"):
        dsn.url_sqlalchemy()
