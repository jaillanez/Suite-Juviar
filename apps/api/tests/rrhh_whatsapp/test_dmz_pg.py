"""infra/042 contra PostgreSQL: cada rol hace sólo lo suyo (bot, Gestión, guardia).

Requiere una base DMZ con las migraciones aplicadas hasta 042 y un usuario administrador:
RRHH_TEST_DSN_ADMIN=postgresql://postgres@127.0.0.1:55442/dmz
Cada rol se prueba conectando como ese rol (``options=-c role=...``).
"""

import os

import psycopg
import pytest
from consulta_publica.bot.repositorio import RepositorioBot
from psycopg.conninfo import make_conninfo

from suite_juviar.modulos.rrhh_whatsapp.infrastructure.dmz import PuertaDMZ

DSN = os.environ.get("RRHH_TEST_DSN_ADMIN")
pytestmark = pytest.mark.skipif(not DSN, reason="sin RRHH_TEST_DSN_ADMIN")

EMPLEADO, OTRO, DESCONOCIDO, PRODUCTOR = "5492649000001", "5492649000002", "5492649000003", "5492649000004"
PDF = b"%PDF-1.4 certificado de prueba " + b"0" * 400


def _como(rol: str) -> str:
    return make_conninfo(DSN, options=f"-c role={rol}")


def _admin(sql: str, *parametros):
    with psycopg.connect(DSN, autocommit=True) as cn:
        cursor = cn.execute(sql, parametros)
        return cursor.fetchall() if cursor.description else None


@pytest.fixture(autouse=True)
def base():
    with psycopg.connect(DSN, autocommit=True) as cn:
        telefonos = [EMPLEADO, OTRO, DESCONOCIDO, PRODUCTOR]
        cn.execute("DELETE FROM fila.aviso_personal WHERE telefono = ANY(%s)", (telefonos,))
        cn.execute("DELETE FROM fila.mensaje_rrhh WHERE telefono = ANY(%s)", (telefonos,))
        cn.execute("DELETE FROM fila.cv_whatsapp WHERE telefono = ANY(%s)", (telefonos,))
        cn.execute("UPDATE consulta.telefono_personal SET recorrido_id = NULL WHERE telefono = ANY(%s)", (telefonos,))
        cn.execute("DELETE FROM fila.aviso_micro WHERE recorrido_id IN "
                   "(SELECT id FROM fila.recorrido_micro WHERE nombre LIKE 'Prueba %')")
        cn.execute("DELETE FROM fila.recorrido_micro WHERE nombre LIKE 'Prueba %'")
        cn.execute("DELETE FROM consulta.telefono_productor WHERE telefono = %s", (PRODUCTOR,))
        for telefono, legajo in ((EMPLEADO, "9001"), (OTRO, "9002")):
            cn.execute("SELECT consulta.guardar_personal(%s, %s, 'PRUEBA, EMPLEADO', 'ENAV', 'personal', 'prueba')",
                       (telefono, legajo))
        cn.execute("INSERT INTO consulta.telefono_productor (telefono, clientecuit) VALUES (%s, '20000000001')",
                   (PRODUCTOR,))
    yield


def _gestion():
    return psycopg.connect(_como("gestion_tablero"), autocommit=True)


def test_el_bot_deja_certificados_y_pedidos_solo_del_personal_activo():
    bot = RepositorioBot(_como("consulta_bot"))
    numero = bot.registrar_rrhh(EMPLEADO, "certificado", "certificado", PDF, "application/pdf", "c.pdf")
    assert numero > 0
    assert bot.registrar_rrhh(EMPLEADO, "epp", "EPP: guantes", None, None, None) > numero
    with pytest.raises(ValueError, match="no está activo"):
        bot.registrar_rrhh(DESCONOCIDO, "epp", "EPP: guantes", None, None, None)
    with pytest.raises(ValueError, match="falta la foto"):
        bot.registrar_rrhh(EMPLEADO, "certificado", "certificado", None, None, None)
    with pytest.raises(ValueError, match="PDF, JPG"):
        bot.registrar_rrhh(EMPLEADO, "certificado", "x", PDF, "image/svg+xml", "c.svg")
    with pytest.raises(psycopg.errors.CheckViolation):  # el tope de tamaño también lo controla la base
        bot.registrar_rrhh(EMPLEADO, "certificado", "x", b"%PDF" + b"0" * 5_000_001, "application/pdf", "c.pdf")


def test_cv_solo_de_numeros_que_no_son_productor_ni_personal():
    bot = RepositorioBot(_como("consulta_bot"))
    assert bot.registrar_cv(DESCONOCIDO, "cv.pdf", PDF, "application/pdf") > 0
    for telefono in (EMPLEADO, PRODUCTOR):
        with pytest.raises(ValueError, match="productor o del personal"):
            bot.registrar_cv(telefono, "cv.pdf", PDF, "application/pdf")
    puerta = PuertaDMZ(_como("gestion_tablero"))
    [cv] = [c for c in puerta.tomar_cvs() if c.telefono == DESCONOCIDO]
    assert cv.contenido == PDF and cv.tipo == "application/pdf"
    puerta.confirmar_cvs([cv.id])
    assert not [c for c in puerta.tomar_cvs() if c.telefono == DESCONOCIDO]
    [(contenido,)] = _admin("SELECT contenido FROM fila.cv_whatsapp WHERE id = %s", int(cv.id))
    assert contenido is None  # el CV ya no queda en la DMZ


def test_gestion_toma_el_certificado_y_el_archivo_se_borra_de_la_dmz():
    bot = RepositorioBot(_como("consulta_bot"))
    numero = bot.registrar_rrhh(EMPLEADO, "certificado", "certificado", PDF, "application/pdf", "c.pdf")
    puerta = PuertaDMZ(_como("gestion_tablero"))
    [mensaje] = [m for m in puerta.tomar_mensajes() if m.id == str(numero)]
    assert (mensaje.legajo, mensaje.archivo, mensaje.archivo_tipo) == ("9001", PDF, "application/pdf")
    puerta.confirmar_mensajes([mensaje.id])
    assert str(numero) not in [m.id for m in puerta.tomar_mensajes()]
    [(archivo,)] = _admin("SELECT archivo FROM fila.mensaje_rrhh WHERE id = %s", numero)
    assert archivo is None


def test_confirmacion_si_no_y_correccion():
    bot = RepositorioBot(_como("consulta_bot"))
    puerta = PuertaDMZ(_como("gestion_tablero"))
    numero = bot.registrar_rrhh(EMPLEADO, "certificado", "certificado", PDF, "application/pdf", "c.pdf")
    assert bot.confirmacion_pendiente(EMPLEADO) is None
    puerta.avisar_lectura(str(numero), "Leímos tu certificado médico:\n• Días: 3", True)
    puerta.avisar_lectura(str(numero), "otra vez", True)  # sincronizar de nuevo no manda dos mensajes
    avisos = [a for a in bot.tomar_avisos_personal() if a["telefono"] == EMPLEADO]
    assert [(a["tipo"], a["texto"]) for a in avisos] == [("certificado", "Leímos tu certificado médico:\n• Días: 3")]
    bot.marcar_aviso_personal(avisos[0]["id"], "wamid.x", None)
    assert bot.confirmacion_pendiente(EMPLEADO) == "esperando"
    assert bot.responder_certificado(EMPLEADO, "correccion", "x") is None  # todavía no dijo que no
    assert bot.responder_certificado(EMPLEADO, "no") == "corrigiendo"
    assert bot.responder_certificado(EMPLEADO, "correccion", "son 5 días") == "no_coincide"
    assert bot.confirmacion_pendiente(EMPLEADO) is None
    estado = puerta.confirmaciones([str(numero)])[str(numero)]
    assert (estado.confirmacion, estado.correccion) == ("no_coincide", "son 5 días")

    otro = bot.registrar_rrhh(OTRO, "certificado", "certificado", PDF, "application/pdf", "c.pdf")
    puerta.avisar_lectura(str(otro), "Leímos tu certificado médico:\n• Días: 2", True)
    assert bot.responder_certificado(OTRO, "si") == "confirmado"
    assert puerta.confirmaciones([str(otro)])[str(otro)].confirmacion == "confirmado"


def test_sin_lectura_no_se_espera_respuesta_y_la_espera_vence():
    bot = RepositorioBot(_como("consulta_bot"))
    puerta = PuertaDMZ(_como("gestion_tablero"))
    numero = bot.registrar_rrhh(EMPLEADO, "certificado", "certificado", PDF, "application/pdf", "c.pdf")
    puerta.avisar_lectura(str(numero), "No pudimos leer los datos. RRHH lo va a revisar.", False)
    assert bot.confirmacion_pendiente(EMPLEADO) is None
    assert puerta.confirmaciones([str(numero)])[str(numero)].confirmacion == "sin_pedir"
    otro = bot.registrar_rrhh(EMPLEADO, "certificado", "certificado", PDF, "application/pdf", "c.pdf")
    puerta.avisar_lectura(str(otro), "Leímos: 3 días", True)
    _admin("UPDATE fila.mensaje_rrhh SET confirmacion_vence = now() - interval '1 minute' WHERE id = %s", otro)
    assert bot.confirmacion_pendiente(EMPLEADO) is None  # una respuesta vieja no se engancha
    assert bot.responder_certificado(EMPLEADO, "si") is None


def test_aviso_del_micro_por_recorrido_sin_duplicados():
    with _gestion() as cn:
        chimbas = cn.execute("SELECT id FROM fila.guardar_recorrido_micro(NULL, 'chimbas', 'Prueba Rawson', true, 'rrhh')").fetchone()[0]
        lavalle = cn.execute("SELECT id FROM fila.guardar_recorrido_micro(NULL, 'lavalle', 'Prueba Lavalle', true, 'rrhh')").fetchone()[0]
        with pytest.raises(psycopg.errors.RaiseException, match="ya hay un recorrido"):
            cn.execute("SELECT fila.guardar_recorrido_micro(NULL, 'chimbas', 'prueba rawson', true, 'rrhh')")
        cn.execute("SELECT consulta.asignar_recorrido_personal(%s, %s, 'rrhh')", (EMPLEADO, chimbas))
        cn.execute("SELECT consulta.asignar_recorrido_personal(%s, %s, 'rrhh')", (OTRO, lavalle))
        [(tipo, actor)] = cn.execute(
            "SELECT tipo, actor FROM consulta.personal_evento WHERE telefono = %s ORDER BY id DESC LIMIT 1",
            (EMPLEADO,)).fetchall()
        assert (tipo, actor) == ("cambio", "rrhh")
    with psycopg.connect(_como("fila_guardia"), autocommit=True) as cn:
        recorridos = cn.execute("SELECT id, personas FROM fila.recorridos_micro('chimbas')").fetchall()
        assert (chimbas, 1) in recorridos and lavalle not in [r[0] for r in recorridos]
        [(_, nombre, destinatarios)] = cn.execute(
            "SELECT * FROM fila.avisar_llegada_micro(%s, 'chimbas', 'guardia:mgomez')", (chimbas,)).fetchall()
        assert (nombre, destinatarios) == ("Prueba Rawson", 1)
        with pytest.raises(psycopg.errors.RaiseException, match="ya se avisó"):
            cn.execute("SELECT * FROM fila.avisar_llegada_micro(%s, 'chimbas', 'guardia:mgomez')", (chimbas,))
        with pytest.raises(psycopg.errors.RaiseException, match="no es de esta bodega"):
            cn.execute("SELECT * FROM fila.avisar_llegada_micro(%s, 'chimbas', 'guardia:mgomez')", (lavalle,))
    bot = RepositorioBot(_como("consulta_bot"))
    avisos = [a for a in bot.tomar_avisos_personal() if a["telefono"] in (EMPLEADO, OTRO)]
    assert [(a["telefono"], a["tipo"], a["recorrido"]) for a in avisos] == [(EMPLEADO, "micro", "Prueba Rawson")]
    bot.marcar_aviso_personal(avisos[0]["id"], "wamid.m", None)
    assert not [a for a in bot.tomar_avisos_personal() if a["telefono"] == EMPLEADO]


def test_el_webhook_encola_el_documento_con_nombre_y_tipo():
    from consulta_publica.bot.meta import MensajeEntrante
    from consulta_publica.bot.repositorio import RepositorioWebhook

    _admin("DELETE FROM consulta.bot_entrada WHERE telefono = %s", DESCONOCIDO)
    _admin("UPDATE consulta.bot_entrada SET estado = 'ignorado' WHERE estado IN ('pendiente', 'tomado')")
    webhook = RepositorioWebhook(_como("consulta_webhook"))
    mensaje = MensajeEntrante("wamid.doc.1", DESCONOCIDO, "document", "mi cv", None, "MEDIA.9", "cv.pdf",
                              "application/pdf")
    assert webhook.encolar(mensaje) and not webhook.encolar(mensaje)
    [pendiente] = RepositorioBot(_como("consulta_bot")).tomar()
    assert (pendiente.media_id, pendiente.media_nombre, pendiente.media_tipo) == ("MEDIA.9", "cv.pdf",
                                                                                  "application/pdf")
    with pytest.raises(psycopg.errors.CheckViolation):
        webhook.encolar(MensajeEntrante("wamid.doc.2", DESCONOCIDO, "document", None, None, "MEDIA.9", "x.exe",
                                        "application/x-msdownload"))


def test_cada_rol_no_puede_lo_de_los_otros():
    with psycopg.connect(_como("consulta_bot"), autocommit=True) as cn:
        for sql in ("SELECT * FROM fila.avisar_llegada_micro(1, 'chimbas', 'x')",
                    "SELECT * FROM fila.mensajes_rrhh_pendientes(5)",
                    "SELECT * FROM fila.guardar_recorrido_micro(NULL, 'chimbas', 'Prueba X', true, 'x')"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cn.execute(sql)
    with psycopg.connect(_como("fila_guardia"), autocommit=True) as cn:
        for sql in ("SELECT * FROM fila.mensaje_rrhh", "SELECT * FROM fila.mensajes_rrhh_pendientes(5)",
                    "SELECT * FROM fila.cv_whatsapp"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cn.execute(sql)
    with _gestion() as cn:
        for sql in ("SELECT fila.recibir_mensaje_rrhh('5492649000001', 'epp', 'x', NULL, NULL, NULL)",
                    "SELECT * FROM fila.avisar_llegada_micro(1, 'chimbas', 'x')",
                    "SELECT * FROM fila.tomar_avisos_personal(5)"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cn.execute(sql)
    with (psycopg.connect(_como("consulta_webhook"), autocommit=True) as cn,
          pytest.raises(psycopg.errors.InsufficientPrivilege)):
        cn.execute("SELECT fila.recibir_cv_whatsapp('5492649000003', 'cv.pdf', NULL, 'application/pdf')")
