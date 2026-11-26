"""infra/043 contra PostgreSQL: los avisos salen de la base con la plantilla y sus parámetros.

Requiere una base DMZ con las migraciones aplicadas hasta 043 y un usuario administrador:
PLANTILLAS_TEST_DSN_ADMIN=postgresql://postgres@127.0.0.1:55443/dmz
Cada corrida usa un productor y teléfonos nuevos, así no choca con lo que ya haya en la base.
"""

import os
import random
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg
import pytest
from consulta_publica.bot.plantillas import CATALOGO
from consulta_publica.bot.repositorio import RepositorioBot
from psycopg.conninfo import make_conninfo

DSN = os.environ.get("PLANTILLAS_TEST_DSN_ADMIN")
pytestmark = pytest.mark.skipif(not DSN, reason="sin PLANTILLAS_TEST_DSN_ADMIN")
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def _admin(sql: str, *parametros):
    with psycopg.connect(DSN, autocommit=True) as cn:
        cursor = cn.execute(sql, parametros)
        return cursor.fetchall() if cursor.description else None


def _como(rol: str, sql: str, *parametros):
    with psycopg.connect(make_conninfo(DSN, options=f"-c role={rol}"), autocommit=True) as cn:
        cursor = cn.execute(sql, parametros)
        return cursor.fetchall() if cursor.description else None


def _bot() -> RepositorioBot:
    return RepositorioBot(make_conninfo(DSN, options="-c role=consulta_bot"))


def _dias_habiles(cantidad: int):
    dia, dias = datetime.now(ZoneInfo("America/Argentina/San_Juan")).date(), []
    while len(dias) < cantidad:
        dia += timedelta(days=1)
        if dia.isoweekday() != 7:
            dias.append(dia)
    return dias


def _largo(dia) -> str:
    return f"{DIAS[dia.weekday()]} {dia:%d/%m}"


@pytest.fixture()
def oferta():
    cuit = f"20{random.randrange(10**8, 10**9)}"
    telefono = f"549264{random.randrange(10**6, 10**7)}"
    _admin("INSERT INTO fila.productor (clientecuit, razonsocial, busqueda) VALUES (%s, 'PÉREZ JUAN ', 'perez juan')",
           cuit)
    _admin("INSERT INTO consulta.telefono_productor (telefono, clientecuit, tareas) VALUES (%s, %s, '{pedir_turnos}')",
           telefono, cuit)
    id_ = _admin(
        """INSERT INTO fila.oferta (pedido, temporada, sede, clientecuit, variedad, kg, kg_a_programar, canal,
                                    pedido_por)
           VALUES (%s, 2027, 'media-agua', %s, 'Syrah', 22000, 22000, 'bodega', 'prueba') RETURNING id""",
        uuid.uuid4(), cuit)[0][0]
    yield id_, telefono
    _admin("DELETE FROM fila.aviso_productor WHERE telefono = %s", telefono)


def _avisos(telefono: str) -> list[dict]:
    return [a for a in _bot().tomar_avisos(50) if a["telefono"] == telefono]


def test_asignar_y_postergar_dejan_la_plantilla_con_sus_parametros(oferta):
    id_, telefono = oferta
    dias = _dias_habiles(2)
    _como("gestion_tablero", "SELECT count(*) FROM fila.asignar_oferta(%s, %s::date[], '{1,1}', '{11000,11000}', "
          "11000, 'prueba', 'Hola, te asignamos los días')", id_, dias)
    [aviso] = _avisos(telefono)
    assert aviso["texto"] == "Hola, te asignamos los días"  # el texto de siempre sigue
    assert aviso["plantilla"] == "turnos_asignados"
    assert aviso["parametros"] == ["PÉREZ JUAN", "Media Agua", "Syrah", _largo(dias[0]), _largo(dias[1]),
                                   "2 camiones"]
    assert CATALOGO["turnos_asignados"].variables == len(aviso["parametros"])

    hasta = _dias_habiles(1)[0] + timedelta(days=14)
    _como("gestion_tablero", "SELECT id FROM fila.detener_oferta(%s, %s, 'prueba', 'Postergamos')", id_, hasta)
    [aviso] = _avisos(telefono)
    assert aviso["plantilla"] == "oferta_postergada"
    assert aviso["parametros"] == ["PÉREZ JUAN", "Media Agua", "Syrah", _largo(hasta)]


def test_aviso_de_mosto_virgen_con_plantilla_y_marca_con_nota():
    telefono = f"549264{random.randrange(10**6, 10**7)}"
    _admin("SELECT consulta.guardar_personal(%s, '9100', 'PRUEBA, MOSTO', 'ENAV', 'personal', 'prueba')", telefono)
    try:
        _como("gestion_tablero", "SELECT fila.encolar_aviso_mosto(%s, 'AB123CD', 'Viñedos del Sur', 4512, 6.5, "
              "'Chimbas')", telefono)
        [aviso] = _avisos(telefono)
        assert aviso["plantilla"] == "mosto_virgen_demorado"
        assert aviso["parametros"] == ["AB123CD", "Viñedos del Sur", "4512", "6.5", "Chimbas"]
        assert CATALOGO["mosto_virgen_demorado"].texto(aviso["parametros"]) == aviso["texto"]

        _bot().marcar_aviso(aviso["id"], "wamid.t", None, "plantilla rechazada (132001); salió como texto")
        [(enviado, nota)] = _admin("SELECT enviado_en IS NOT NULL, ultimo_error FROM fila.aviso_productor "
                                   "WHERE id = %s", aviso["id"])
        assert enviado and "132001" in nota
    finally:
        _admin("DELETE FROM fila.aviso_productor WHERE telefono = %s", telefono)
