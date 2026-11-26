"""«¿Olvidaste tu contraseña?»: enlace por correo, un solo uso, 30 minutos y límites."""

import hashlib
import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from suite_juviar.plataforma.identidad.api.dependencias import (
    PERMISOS_POR_PERFIL,
    configurar_envio_correo,
    configurar_ingreso,
    configurar_recuperacion,
    enviar_correo_interno,
)
from suite_juviar.plataforma.identidad.api.ingreso import router
from suite_juviar.plataforma.identidad.application.ingreso import ServicioIngreso
from suite_juviar.plataforma.identidad.application.recuperacion import ServicioRecuperacion
from suite_juviar.plataforma.identidad.domain.recuperacion import RESPUESTA_PEDIDO
from suite_juviar.plataforma.identidad.domain.usuarios import IngresoInvalido
from suite_juviar.plataforma.identidad.infrastructure.recuperacion_sqlite import RecuperacionSQLite
from suite_juviar.plataforma.identidad.infrastructure.usuarios_sqlite import UsuariosSQLite

CLAVE = "clave-larga-1"
NUEVA = "otra-clave-larga-2"


class Reloj:
    def __init__(self):
        self.ahora = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)

    def __call__(self):
        return self.ahora

    def avanzar(self, **delta):
        self.ahora += timedelta(**delta)


class Buzon:
    def __init__(self):
        self.enviados: list[tuple[str, str, str]] = []
        self.falla: Exception | None = None

    def __call__(self, destino, asunto, cuerpo):
        if self.falla:
            raise self.falla
        self.enviados.append((destino, asunto, cuerpo))
        return True

    def token(self, indice=-1):
        return re.search(r"/restablecer/#(\S+)", self.enviados[indice][2]).group(1)


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    monkeypatch.setenv("SJ_IDENTIDAD_REAL", "1")
    monkeypatch.setenv("SJ_COOKIE_SEGURA", "0")
    ruta = tmp_path / "u.sqlite3"
    usuarios = UsuariosSQLite(ruta)
    ingreso = ServicioIngreso(usuarios, frozenset(PERMISOS_POR_PERFIL))
    reloj, buzon = Reloj(), Buzon()
    configurar_envio_correo(buzon)
    servicio = ServicioRecuperacion(
        usuarios, RecuperacionSQLite(ruta), enviar_correo_interno, "https://juviar-enav.com.ar/",
        reloj=reloj, ejecutar=lambda tarea: tarea(),
    )
    configurar_ingreso(ingreso)
    configurar_recuperacion(servicio)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    yield ingreso, servicio, reloj, buzon, TestClient(app)
    configurar_ingreso(None)
    configurar_recuperacion(None)
    configurar_envio_correo(None)


def alta(ingreso, email="ana@enav.com", activo=True, debe_cambiar=False):
    usuario = ingreso.crear_usuario("test", email, "Ana", "MEDICO", ["ENAV"], CLAVE)
    guardada = ingreso.repositorio.obtener_por_email(usuario.email)[1]
    ingreso.repositorio.cambiar_clave(usuario.id, guardada, debe_cambiar=debe_cambiar)
    if not activo:
        ingreso.modificar_usuario("test", usuario.id, nombre="Ana", perfil="MEDICO", empresas=["ENAV"],
                                  activo=False)
    return usuario


def pedir(cliente, email):
    return cliente.post("/api/v1/ingreso/recuperar", json={"email": email})


def restablecer(cliente, token, clave=NUEVA):
    return cliente.post("/api/v1/ingreso/restablecer", json={"token": token, "clave": clave})


def acciones(ingreso):
    return [e["accion"] for e in ingreso.repositorio.eventos()]


def test_misma_respuesta_con_correo_existente_inexistente_o_inactivo(entorno):
    ingreso, _, _, buzon, cliente = entorno
    alta(ingreso, "ana@enav.com")
    alta(ingreso, "baja@enav.com", activo=False)
    respuestas = [pedir(cliente, e) for e in ("ANA@enav.com", "nadie@enav.com", "baja@enav.com", "no-es-correo")]
    assert {r.status_code for r in respuestas} == {200}
    assert {r.text for r in respuestas} == {respuestas[0].text}
    assert respuestas[0].json()["mensaje"] == RESPUESTA_PEDIDO
    assert [d for d, _, _ in buzon.enviados] == ["ana@enav.com"]
    _destino, asunto, cuerpo = buzon.enviados[0]
    assert "30 minutos" in cuerpo and "ignorá" in cuerpo and asunto
    assert "https://juviar-enav.com.ar/restablecer/#" in cuerpo
    assert CLAVE not in cuerpo and "scrypt" not in cuerpo
    assert acciones(ingreso).count("RECUPERACION_SIN_CUENTA") == 2


def test_el_envio_corre_aparte_y_la_respuesta_no_lo_espera(entorno):
    ingreso, servicio, _, buzon, cliente = entorno
    alta(ingreso)
    pendientes = []
    servicio.ejecutar = pendientes.append
    assert pedir(cliente, "ana@enav.com").status_code == 200
    assert buzon.enviados == [] and len(pendientes) == 1
    pendientes[0]()
    assert len(buzon.enviados) == 1


def test_el_token_se_guarda_solo_como_resumen_y_sirve_una_vez(entorno):
    ingreso, servicio, _, buzon, cliente = entorno
    usuario = alta(ingreso, debe_cambiar=True)
    pedir(cliente, "ana@enav.com")
    token = buzon.token()
    assert len(token) >= 43  # 256 bits en base64url
    filas = servicio.enlaces._cn.execute("SELECT * FROM recuperacion_enlace").fetchall()
    assert [f["token_sha256"] for f in filas] == [hashlib.sha256(token.encode()).hexdigest()]
    assert token not in str([dict(f) for f in filas])
    sesion, _ = ingreso.ingresar("ana@enav.com", CLAVE)
    assert restablecer(cliente, token).status_code == 200
    assert restablecer(cliente, token, "tercera-clave-3").status_code == 410
    assert ingreso.resolver(sesion) is None  # se cerraron todas las sesiones
    assert ingreso.repositorio.obtener(usuario.id).debe_cambiar_clave is False
    with pytest.raises(IngresoInvalido):
        ingreso.ingresar("ana@enav.com", CLAVE)
    ingreso.ingresar("ana@enav.com", NUEVA)
    eventos = ingreso.repositorio.eventos()
    assert "RECUPERACION_CLAVE_CAMBIADA" in [e["accion"] for e in eventos]
    assert all(token not in str(e) and NUEVA not in str(e) for e in eventos)


def test_el_enlace_vence_a_los_30_minutos(entorno):
    ingreso, _, reloj, buzon, cliente = entorno
    alta(ingreso)
    pedir(cliente, "ana@enav.com")
    reloj.avanzar(minutes=29, seconds=59)
    token = buzon.token()
    assert restablecer(cliente, token, "corta").status_code == 400  # todavía vigente
    reloj.avanzar(seconds=1)
    respuesta = restablecer(cliente, token)
    assert respuesta.status_code == 410 and "Pedí uno nuevo" in respuesta.json()["detail"]
    ingreso.ingresar("ana@enav.com", CLAVE)


def test_pedir_otro_enlace_anula_el_anterior(entorno):
    ingreso, _, _, buzon, cliente = entorno
    alta(ingreso)
    pedir(cliente, "ana@enav.com")
    pedir(cliente, "ana@enav.com")
    primero, segundo = buzon.token(0), buzon.token(1)
    assert primero != segundo
    assert restablecer(cliente, primero).status_code == 410
    assert restablecer(cliente, segundo).status_code == 200


def test_reglas_de_la_clave_y_el_enlace_sigue_sirviendo_para_reintentar(entorno):
    ingreso, _, _, buzon, cliente = entorno
    alta(ingreso)
    pedir(cliente, "ana@enav.com")
    token = buzon.token()
    for mala in ("corta", " con-espacio-adelante", "con-espacio-atras "):
        assert restablecer(cliente, token, mala).status_code == 400
    assert restablecer(cliente, token).status_code == 200
    assert restablecer(cliente, "inventado").status_code == 410


def test_cuenta_desactivada_despues_de_pedir_el_enlace(entorno):
    ingreso, _, _, buzon, cliente = entorno
    usuario = alta(ingreso)
    pedir(cliente, "ana@enav.com")
    ingreso.modificar_usuario("test", usuario.id, nombre="Ana", perfil="MEDICO", empresas=["ENAV"], activo=False)
    assert restablecer(cliente, buzon.token()).status_code == 410


def test_limite_por_correo(entorno):
    ingreso, _, reloj, buzon, cliente = entorno
    alta(ingreso)
    respuestas = [pedir(cliente, "ana@enav.com") for _ in range(5)]
    assert {r.text for r in respuestas} == {respuestas[0].text}
    assert len(buzon.enviados) == 3
    assert "RECUPERACION_LIMITE" in acciones(ingreso)
    reloj.avanzar(hours=1, seconds=1)
    pedir(cliente, "ana@enav.com")
    assert len(buzon.enviados) == 4


def test_limite_por_equipo_de_origen(entorno):
    ingreso, _, _, buzon, cliente = entorno
    alta(ingreso, "ana@enav.com")
    for i in range(10):
        pedir(cliente, f"otro{i}@enav.com")
    pedir(cliente, "ana@enav.com")
    assert buzon.enviados == []  # el undécimo pedido desde el mismo equipo no hace nada
    acciones_registradas = acciones(ingreso)
    assert acciones_registradas.count("RECUPERACION_LIMITE") == 1


def test_el_limite_se_cuenta_en_la_base_y_sobrevive_un_reinicio(entorno, tmp_path):
    ingreso, _servicio, reloj, buzon, cliente = entorno
    alta(ingreso)
    for _ in range(3):
        pedir(cliente, "ana@enav.com")
    otro = ServicioRecuperacion(ingreso.repositorio, RecuperacionSQLite(tmp_path / "u.sqlite3"),
                                enviar_correo_interno, "https://x", reloj=reloj, ejecutar=lambda t: t())
    otro.pedir("ana@enav.com", "testclient")
    assert len(buzon.enviados) == 3


def test_sin_casilla_configurada_no_rompe_y_queda_registrado(entorno):
    ingreso, servicio, _, _buzon, cliente = entorno
    alta(ingreso)
    configurar_envio_correo(None)
    respuesta = pedir(cliente, "ana@enav.com")
    assert respuesta.status_code == 200 and respuesta.json()["mensaje"] == RESPUESTA_PEDIDO
    eventos = ingreso.repositorio.eventos()
    assert eventos[0]["accion"] == "RECUPERACION_ERROR_ENVIO"
    assert "casilla" in eventos[0]["detalle"]
    assert servicio.enlaces._cn.execute("SELECT COUNT(*) FROM recuperacion_enlace").fetchone()[0] == 0


def test_si_falla_el_envio_la_respuesta_es_la_misma(entorno):
    ingreso, _, _, buzon, cliente = entorno
    alta(ingreso)
    buzon.falla = OSError("smtp caído")
    respuesta = pedir(cliente, "ana@enav.com")
    assert respuesta.status_code == 200 and respuesta.json()["mensaje"] == RESPUESTA_PEDIDO
    assert ingreso.repositorio.eventos()[0]["accion"] == "RECUPERACION_ERROR_ENVIO"


def test_sin_envio_conectado_no_se_manda_nada():
    configurar_envio_correo(None)
    assert enviar_correo_interno("a@b.com", "x", "y") is False
