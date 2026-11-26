"""infra/044 contra PostgreSQL: acceso por cuenta, CUIT o patente y comprobante DDJJ.

Requiere una base DMZ con las migraciones aplicadas hasta 044 y un usuario administrador:
ACCESO_TEST_DSN_ADMIN=postgresql://postgres@127.0.0.1:55443/dmz
Cada corrida usa productores, patentes y teléfonos nuevos, así no choca con lo que ya haya.
"""

import os
import random
import uuid

import psycopg
import pytest
from consulta_publica.bot.dialogo import Estado, IdentificacionBloqueada
from consulta_publica.bot.repositorio import IdentificadorBot, RepositorioBot
from consulta_publica.lectura.repositorio_descargas import RepositorioDescargasPg
from psycopg.conninfo import make_conninfo

DSN = os.environ.get("ACCESO_TEST_DSN_ADMIN")
pytestmark = pytest.mark.skipif(not DSN, reason="sin ACCESO_TEST_DSN_ADMIN")


def _admin(sql: str, *parametros):
    with psycopg.connect(DSN, autocommit=True) as cn:
        cursor = cn.execute(sql, parametros)
        return cursor.fetchall() if cursor.description else None


def _dsn_bot() -> str:
    return make_conninfo(DSN, options="-c role=consulta_bot")


def _cuit() -> str:
    """CUIT nuevo con dígito verificador válido."""
    base = f"20{random.randrange(10**7, 10**8)}"
    suma = sum(int(d) * p for d, p in zip(base, (5, 4, 3, 2, 7, 6, 5, 4, 3, 2), strict=True))
    return base + str({11: 0, 10: 9}.get(11 - suma % 11, 11 - suma % 11))


@pytest.fixture()
def datos():
    sufijo = random.randrange(10**4, 10**5)
    juan, finca, inscripto = _cuit(), _cuit(), _cuit()
    codigo_juan, codigo_finca = f"Q{sufijo}", f"R{sufijo}"
    patente, patente_fila = f"ZZ{sufijo % 1000:03d}QA", f"ZQ{sufijo % 1000:03d}WB"
    telefono = f"549264{random.randrange(10**6, 10**7)}"
    for cuit, razon, codigo in ((juan, "PEREZ JUAN", codigo_juan), (finca, "FINCA DEL SOL SA", codigo_finca)):
        _admin("INSERT INTO fila.productor (clientecuit, razonsocial, busqueda, codigos) VALUES (%s, %s, %s, %s)",
               cuit, razon, razon.lower(), [codigo])
    # El mismo inscripto entregó para las dos cuentas; la patente sólo para la de Juan.
    for cuit, codigo, ciu in ((juan, codigo_juan, f"00000{sufijo}"), (finca, codigo_finca, f"1{sufijo}")):
        _admin("""INSERT INTO consulta.descarga_publica (sede, ciu, id_origen, fecha, clientecuit, neto, variedad,
                                                       azucar, estado, actualizado_en, clientecodigo, patente,
                                                       cuit_inscripto)
                  VALUES ('chimbas', %s, %s, now() - interval '10 days', %s, 23450, 'MALBEC', 23.5, 'descargado',
                          now(), %s, %s, %s)""",
               ciu, str(uuid.uuid4()), cuit, codigo, patente if cuit == juan else None, inscripto)
    # Una patente que sólo se registró en la fila de camiones (QR del portón).
    _admin("""INSERT INTO fila.viaje (id_cliente, ticket, sede, patente, origen, estado, confirmado_en, clientecuit)
              VALUES (%s, %s, 'chimbas', %s, 'qr', 'descargado', now(), %s)""",
           uuid.uuid4(), "t" * 43 + str(sufijo), patente_fila, finca)
    yield {"juan": juan, "finca": finca, "inscripto": inscripto, "codigo_juan": codigo_juan,
           "patente": patente, "patente_fila": patente_fila, "telefono": telefono, "sufijo": sufijo}
    _admin("DELETE FROM consulta.bot_vinculo WHERE telefono = %s", telefono)
    _admin("DELETE FROM consulta.bot_identificacion WHERE telefono = %s", telefono)


def test_identifica_por_cuenta_cuit_y_patente(datos):
    buscar = IdentificadorBot(_dsn_bot(), datos["telefono"]).buscar
    [por_codigo] = buscar("cuenta", datos["codigo_juan"])
    assert (por_codigo.clientecuit, por_codigo.codigo) == (datos["juan"], datos["codigo_juan"])
    assert [c.clientecuit for c in buscar("cuit", datos["juan"])] == [datos["juan"]]
    # El CUIT del inscripto trae las dos cuentas para las que entregó.
    assert {c.clientecuit for c in buscar("cuit", datos["inscripto"])} == {datos["juan"], datos["finca"]}
    assert [c.clientecuit for c in buscar("patente", datos["patente"])] == [datos["juan"]]
    assert [c.clientecuit for c in buscar("patente", datos["patente_fila"])] == [datos["finca"]]
    assert buscar("cuenta", "X00000") == []


def test_corta_despues_de_los_intentos_sin_resultado(datos):
    identificador = IdentificadorBot(_dsn_bot(), datos["telefono"], maximo=3)
    for _ in range(3):
        assert identificador.buscar("cuenta", "X00000") == []
    with pytest.raises(IdentificacionBloqueada):
        identificador.buscar("cuenta", datos["codigo_juan"])


def test_vinculo_solo_para_lo_identificado_y_salir(datos):
    bot, telefono = RepositorioBot(_dsn_bot()), datos["telefono"]
    [juan] = bot.identificador(telefono).buscar("cuenta", datos["codigo_juan"])
    finca = bot.cuentas_por_cuit([datos["finca"]])[0]
    with pytest.raises(ValueError, match="cuenta_no_identificada"):
        bot.vincular(telefono, finca)  # ese teléfono nunca la identificó
    bot.vincular(telefono, juan)
    assert bot.vinculo(telefono) == juan
    # El bot no puede escribir el vínculo a mano: sólo con bot_vincular.
    with psycopg.connect(_dsn_bot()) as cn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cn.execute("INSERT INTO consulta.bot_vinculo (telefono, clientecuit, por, dato) "
                   "VALUES (%s, %s, 'cuit', 'x')", (telefono, datos["finca"]))
    bot.desvincular(telefono)
    assert bot.vinculo(telefono) is None


def test_sesion_guarda_las_candidatas(datos):
    bot, telefono = RepositorioBot(_dsn_bot()), datos["telefono"]
    bot.guardar_estado(telefono, Estado("elegir_vinculo", candidatas=(datos["finca"], datos["juan"])))
    estado, caducada = bot.estado_y_caducidad(telefono)
    assert estado.candidatas == (datos["finca"], datos["juan"]) and not caducada
    assert [c.clientecuit for c in bot.cuentas_por_cuit(estado.candidatas)] == [datos["finca"], datos["juan"]]
    _admin("DELETE FROM consulta.bot_sesion WHERE telefono = %s", telefono)


def test_comprobante_por_ciu_solo_de_la_cuenta_activa(datos):
    consultas = RepositorioDescargasPg(_dsn_bot())
    ciu = str(datos["sufijo"])  # sin los ceros de adelante
    comprobante = consultas.comprobante(datos["juan"], ciu, "PEREZ JUAN", "?")
    assert comprobante.ciu == f"00000{datos['sufijo']}" and comprobante.cuenta == datos["codigo_juan"]
    assert comprobante.neto == 23450 and comprobante.azucar == 23.5
    assert consultas.comprobante(datos["finca"], f"00000{datos['sufijo']}", "FINCA", "?") is None
    assert consultas.comprobante(datos["finca"], None, "FINCA", "?").ciu == f"1{datos['sufijo']}"


def test_bitacora_con_telefono(datos):
    bot = RepositorioBot(_dsn_bot())
    bot.registrar_consulta(datos["juan"], "whatsapp:comprobante", 1, datos["telefono"])
    [(cliente, telefono)] = _admin(
        "SELECT cliente, telefono FROM consulta.bitacora_consulta WHERE clientecuit = %s", datos["juan"])
    assert (cliente, telefono) == ("bot-whatsapp-vinculo", datos["telefono"])
