"""Sesión orgánica y foto de patente contra una base DMZ con todas las actualizaciones.

FILA_PRUEBA_DMZ_ADMIN apunta a esa base con un usuario administrador; la consola se
prueba con el rol fila_guardia (clave «x»). Sin la variable, se saltea.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from fila_app.repositorio import RepositorioFila

from modulos.fila.organica import BLOQUEO_CONVENCIONAL

ADMIN = os.environ.get("FILA_PRUEBA_DMZ_ADMIN")
pytestmark = pytest.mark.skipif(not ADMIN, reason="sin FILA_PRUEBA_DMZ_ADMIN")
ORGANICO, COMUN = "20111111112", "20999999990"


def _guardia() -> RepositorioFila:
    datos = psycopg.conninfo.conninfo_to_dict(ADMIN)
    datos.update(user="fila_guardia", password="x")
    return RepositorioFila(psycopg.conninfo.make_conninfo(**datos))


def _admin(sql: str, *parametros):
    with psycopg.connect(ADMIN, autocommit=True) as cn:
        cursor = cn.execute(sql, parametros or None)
        return cursor.fetchall() if cursor.description else None


@pytest.fixture()
def base():
    _admin("""DELETE FROM fila.foto_patente; DELETE FROM fila.sesion_organica;
              DELETE FROM fila.evento; DELETE FROM fila.viaje WHERE sede = 'chimbas'""")
    _admin("""INSERT INTO fila.productor_organico (clientecuit, certificadora, cargado_por)
              VALUES ('20111111112', 'OIA', 'prueba') ON CONFLICT DO NOTHING""")
    _admin("""SELECT fila.fijar_parametro_organica('chimbas', true, 'ambos', 'manual', NULL, 15, 'prueba')""")
    return _guardia()


def _alta(repo, patente, cuit, organica):
    return repo.alta_directa({
        "id_cliente": uuid4(), "momento_cliente": datetime.now(UTC), "sede": "chimbas",
        "patente": patente, "productor": "Productor", "clientecuit": cuit,
        "declara_organica": organica}, "guardia:prueba")


def _accion(repo, viaje, accion):
    return repo.accionar(viaje["id"], accion, "guardia:prueba", uuid4(), datetime.now(UTC))


def test_sesion_bloquea_convencional_y_marca_como_entra(base):
    repo = base
    comun = _alta(repo, "AA111AA", COMUN, False)
    organico = _alta(repo, "BB222BB", ORGANICO, True)

    tablero = repo.tablero("chimbas")
    assert [x["id"] for x in tablero["espera"]] == [comun["id"], organico["id"]]  # sin prioridad
    assert tablero["espera"][1]["organico"] and not tablero["organica"]["abierta"]

    assert repo.sesion_organica("chimbas", True, "guardia:prueba")["abierta"]
    with pytest.raises(ValueError, match="ya está abierta"):
        repo.sesion_organica("chimbas", True, "guardia:prueba")
    tablero = repo.tablero("chimbas")
    assert [x["id"] for x in tablero["espera"]] == [organico["id"], comun["id"]]  # la orgánica primero
    with pytest.raises(ValueError, match=BLOQUEO_CONVENCIONAL[:30]):
        _accion(repo, comun, "llamar")
    assert _accion(repo, organico, "llamar")["recibida_como"] == "organica"

    repo.guardar_foto(organico["id"], b"\xff\xd8\xff" + b"0" * 2000, "image/jpeg", "guardia:prueba")
    assert repo.tablero("chimbas")["llamados"][0]["foto"]

    assert not repo.sesion_organica("chimbas", False, "guardia:prueba")["abierta"]
    assert _accion(repo, organico, "paso")["estado"] == "en_bascula"  # entró dentro de la sesión
    assert _accion(repo, comun, "llamar")["recibida_como"] == "convencional"


def test_organica_sin_sesion_entra_como_convencional_y_respeta_quien_abre(base):
    repo = base
    organico = _alta(repo, "CC333CC", ORGANICO, True)
    assert _accion(repo, organico, "llamar")["recibida_como"] == "convencional"
    assert _accion(repo, organico, "no_vino")["recibida_como"] is None

    _admin("SELECT fila.fijar_parametro_organica('chimbas', true, 'bascula', 'manual', NULL, 15, 'prueba')")
    with pytest.raises(ValueError, match="la báscula"):
        repo.sesion_organica("chimbas", True, "guardia:prueba")


def test_dias_de_prioridad_y_lugar_en_el_ticket(base):
    repo = base
    comun = _alta(repo, "DD444DD", COMUN, False)
    organico = _alta(repo, "EE555EE", ORGANICO, True)
    ticket = _admin("SELECT ticket FROM fila.viaje WHERE id = %s", organico["id"])[0][0]
    assert _admin("SELECT posicion FROM fila.leer_ticket(%s)", ticket)[0][0] == 2

    _admin("SELECT fila.fijar_parametro_organica('chimbas', true, 'ambos', 'manual', current_date, 15, 'prueba')")
    assert [x["id"] for x in repo.tablero("chimbas")["espera"]] == [organico["id"], comun["id"]]
    assert _admin("SELECT posicion FROM fila.leer_ticket(%s)", ticket)[0][0] == 1
    # Prioridad no es sesión: la convencional se puede llamar y la orgánica entra como convencional.
    assert _accion(repo, organico, "llamar")["recibida_como"] == "convencional"


def test_franjas_fijas(base):
    _admin("SELECT fila.fijar_parametro_organica('chimbas', true, 'ambos', 'fijas', NULL, 15, 'prueba')")
    _admin("""SELECT fila.fijar_franjas_organica('chimbas', ARRAY[1]::smallint[], ARRAY['08:00']::time[],
                                                ARRAY['12:00']::time[], 'prueba')""")
    dentro = _admin("SELECT abierta, origen FROM fila.estado_organica('chimbas', '2027-02-01 10:00-03')")
    fuera = _admin("SELECT abierta FROM fila.estado_organica('chimbas', '2027-02-01 12:00-03')")
    martes = _admin("SELECT abierta FROM fila.estado_organica('chimbas', '2027-02-02 10:00-03')")
    assert dentro == [(True, "franja")] and fuera == [(False,)] and martes == [(False,)]
    with pytest.raises(ValueError, match="franjas"):
        base.sesion_organica("chimbas", True, "guardia:prueba")
    with pytest.raises(psycopg.errors.RaiseException, match="superponen"):
        _admin("""SELECT fila.fijar_franjas_organica('chimbas', ARRAY[1,1]::smallint[],
                      ARRAY['08:00','11:00']::time[], ARRAY['12:00','13:00']::time[], 'prueba')""")


def test_guardia_no_puede_tocar_parametros(base):
    with base.conexion() as cn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cn.execute("SELECT fila.fijar_parametro_organica('chimbas', false, 'ambos', 'manual', NULL, 15, 'x')")
