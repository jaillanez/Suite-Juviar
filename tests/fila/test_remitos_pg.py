"""Remitos de salida y mensajes de mantenimiento contra la base DMZ (infra/041).

FILA_PRUEBA_DMZ_ADMIN apunta a una base con todas las actualizaciones; los roles usan la clave «x».
"""

from __future__ import annotations

import json
import os
from uuid import uuid4

import psycopg
import pytest
from fila_app.repositorio import RepositorioFila
from suite_juviar.modulos.activos.infrastructure.guardia_dmz import PuertaDMZ

ADMIN = os.environ.get("FILA_PRUEBA_DMZ_ADMIN")
pytestmark = pytest.mark.skipif(not ADMIN, reason="sin FILA_PRUEBA_DMZ_ADMIN")
PERSONAL, PRODUCTOR = "5492644000001", "5492644000002"


def _dsn(usuario: str) -> str:
    datos = psycopg.conninfo.conninfo_to_dict(ADMIN)
    datos.update(user=usuario, password="x")
    return psycopg.conninfo.make_conninfo(**datos)


def _admin(sql: str, *parametros):
    with psycopg.connect(ADMIN, autocommit=True) as cn:
        cursor = cn.execute(sql, parametros or None)
        return cursor.fetchall() if cursor.description else None


def _como(usuario: str, sql: str, *parametros):
    with psycopg.connect(_dsn(usuario), autocommit=True) as cn:
        cursor = cn.execute(sql, parametros or None)
        return cursor.fetchall() if cursor.description else None


@pytest.fixture()
def base():
    _admin("DELETE FROM fila.remito_salida; DELETE FROM fila.mensaje_mantenimiento")
    _admin("""INSERT INTO consulta.telefono_personal (telefono, legajo, nombre, empresa, tipo, alta_por, actualizado_por)
              VALUES (%s, '77', 'Pedro Mantenimiento', 'ENAV', 'personal', 'prueba', 'prueba')
              ON CONFLICT (telefono) DO UPDATE SET activo = true""", PERSONAL)


def _publicar(numero: int, sede: str = "chimbas") -> str:
    remito_id = str(uuid4())
    _como("gestion_tablero", "SELECT fila.publicar_remito(%s, %s, %s, 'Taller Pérez', 'Bobinado', %s::jsonb, 'papel', 'encargado')",
          remito_id, numero, sede, json.dumps([{"descripcion": "Bomba", "codigo": "BOM-0001", "cantidad": 1}]))
    return remito_id


def test_la_guardia_ve_el_remito_de_su_bodega_y_marca_la_salida(base):
    remito_id = _publicar(1)
    otro = _publicar(2, "lavalle")
    guardia = RepositorioFila(_dsn("fila_guardia"))
    assert [r["numero"] for r in guardia.tablero("chimbas")["remitos"]] == [1]
    with pytest.raises(ValueError, match="no es de esta bodega"):
        guardia.salida_remito(otro, "chimbas", "guardia:juan")
    guardia.salida_remito(remito_id, "chimbas", "guardia:juan")
    assert guardia.tablero("chimbas")["remitos"] == []
    with pytest.raises(ValueError, match="ya salió"):
        guardia.salida_remito(remito_id, "chimbas", "guardia:juan")

    puerta = PuertaDMZ(_dsn("gestion_tablero"))
    salidas = puerta.salidas([remito_id, otro])
    assert list(salidas) == [remito_id] and salidas[remito_id].salio_por == "guardia:juan"
    with pytest.raises(ValueError, match="ya salió"):
        puerta.anular(remito_id, "encargado")


def test_un_remito_anulado_no_puede_salir(base):
    remito_id = _publicar(3)
    PuertaDMZ(_dsn("gestion_tablero")).anular(remito_id, "encargado")
    guardia = RepositorioFila(_dsn("fila_guardia"))
    assert guardia.tablero("chimbas")["remitos"] == []
    with pytest.raises(ValueError, match="anulado"):
        guardia.salida_remito(remito_id, "chimbas", "guardia:juan")


def test_cada_rol_solo_usa_sus_funciones(base):
    remito_id = _publicar(4)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _como("gestion_tablero", "SELECT * FROM fila.marcar_salida_remito(%s, 'chimbas', 'x')", remito_id)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _como("fila_guardia", "SELECT fila.anular_remito(%s, 'x')", remito_id)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _como("consulta_bot", "SELECT * FROM fila.mensajes_mantenimiento_pendientes(10)")


def test_el_bot_solo_acepta_mensajes_del_personal_y_gestion_los_toma_una_vez(base):
    _como("consulta_bot", "SELECT fila.recibir_mensaje_mantenimiento(%s, 'BOM-0001 sale a taller', NULL, NULL)", PERSONAL)
    with pytest.raises(psycopg.errors.RaiseException, match="Personal en el bot"):
        _como("consulta_bot", "SELECT fila.recibir_mensaje_mantenimiento(%s, 'hola', NULL, NULL)", PRODUCTOR)
    puerta = PuertaDMZ(_dsn("gestion_tablero"))
    mensajes = puerta.tomar_mensajes()
    assert [(m.nombre, m.texto) for m in mensajes] == [("Pedro Mantenimiento", "BOM-0001 sale a taller")]
    puerta.confirmar_mensajes([m.id for m in mensajes])
    assert puerta.tomar_mensajes() == []


def test_el_webhook_encola_la_foto_y_el_bot_la_toma_con_su_identificador(base):
    from consulta_publica.bot.meta import MensajeEntrante
    from consulta_publica.bot.repositorio import RepositorioBot, RepositorioWebhook

    _admin("DELETE FROM consulta.bot_entrada")
    wamid = f"w.{uuid4().hex}"
    RepositorioWebhook(_dsn("consulta_webhook")).encolar(
        MensajeEntrante(wamid, PERSONAL, "image", "BOM-0001", None, "MEDIA.9"))
    tomado = RepositorioBot(_dsn("consulta_bot")).tomar()
    assert [(p.tipo, p.texto, p.media_id) for p in tomado] == [("image", "BOM-0001", "MEDIA.9")]
