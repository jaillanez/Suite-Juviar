"""El bot sólo informa a contactos con la tarea ver_informes."""

import os

import psycopg
import pytest
from consulta_publica.bot.repositorio import RepositorioBot

DSN = os.environ.get("FILA_TEST_DSN_ADMIN")
pytestmark = pytest.mark.skipif(not DSN, reason="sin FILA_TEST_DSN_ADMIN")


@pytest.fixture()
def repo():
    with psycopg.connect(DSN, autocommit=True) as cn:
        cn.execute("CREATE SCHEMA IF NOT EXISTS consulta")
        cn.execute("DROP TABLE IF EXISTS consulta.telefono_productor")
        cn.execute(
            """CREATE TABLE consulta.telefono_productor(
               telefono text, clientecuit text, activo boolean NOT NULL DEFAULT true,
               tareas text[] NOT NULL DEFAULT '{ver_informes}',
               PRIMARY KEY(telefono, clientecuit))"""
        )
        cn.execute(
            """INSERT INTO consulta.telefono_productor
               (telefono,clientecuit,activo,tareas) VALUES
               ('549001','20-A',true,'{ver_informes,pedir_turnos,administrar_contactos}'),
               ('549002','20-A',true,'{pedir_turnos}'),
               ('549003','20-A',false,'{ver_informes}'),
               ('549004','20-A',true,'{ver_informes}'),
               ('549004','20-B',true,'{pedir_turnos}')"""
        )
    return RepositorioBot(DSN)


def test_propietario_ve_informes(repo):
    assert repo.productores("549001") == ["20-A"]


def test_encargado_que_solo_pide_turnos_no_ve_informes(repo):
    assert repo.productores("549002") == []


def test_contacto_dado_de_baja_no_ve_nada(repo):
    assert repo.productores("549003") == []


def test_con_dos_productores_ve_solo_donde_tiene_la_tarea(repo):
    assert repo.productores("549004") == ["20-A"]
