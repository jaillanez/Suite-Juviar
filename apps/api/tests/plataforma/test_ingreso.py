import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from suite_juviar.plataforma.identidad.api import dependencias
from suite_juviar.plataforma.identidad.api.dependencias import (
    PERMISOS_POR_PERFIL,
    configurar_ingreso,
    exigir_permiso,
)
from suite_juviar.plataforma.identidad.api.ingreso import router, usuarios
from suite_juviar.plataforma.identidad.application.ingreso import ServicioIngreso
from suite_juviar.plataforma.identidad.domain.usuarios import IngresoInvalido
from suite_juviar.plataforma.identidad.infrastructure.usuarios_sqlite import UsuariosSQLite

CLAVE = "clave-larga-1"


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    monkeypatch.setenv("SJ_IDENTIDAD_REAL", "1")
    monkeypatch.setenv("SJ_COOKIE_SEGURA", "0")
    servicio = ServicioIngreso(UsuariosSQLite(tmp_path / "u.sqlite3"), frozenset(PERMISOS_POR_PERFIL))
    configurar_ingreso(servicio)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.include_router(usuarios, prefix="/api/v1")

    @app.get("/api/v1/salud-protegida", dependencies=[Depends(exigir_permiso("salud.diagnostico.leer"))])
    def protegida():
        return {"ok": True}

    yield servicio, app
    configurar_ingreso(None)


def alta(servicio, email, perfil, cambiar=False):
    usuario = servicio.crear_usuario("test", email, "Nombre", perfil, "ENAV", CLAVE)
    if not cambiar:
        guardada = servicio.repositorio.obtener_por_email(usuario.email)[1]
        servicio.repositorio.cambiar_clave(usuario.id, guardada, debe_cambiar=False)
    return usuario


def entrar(cliente, email, clave=CLAVE):
    return cliente.post("/api/v1/ingreso", json={"email": email, "clave": clave})


def test_ingreso_correcto_e_incorrecto_y_salida(entorno):
    servicio, app = entorno
    alta(servicio, "medica@enav.com", "MEDICO")
    cliente = TestClient(app)
    assert entrar(cliente, "medica@enav.com", "otra-clave-x").status_code == 401
    assert entrar(cliente, "nadie@enav.com").status_code == 401
    respuesta = entrar(cliente, "MEDICA@enav.com")
    assert respuesta.status_code == 200
    assert respuesta.json()["perfil"] == "MEDICO"
    assert CLAVE not in respuesta.text and "scrypt" not in respuesta.text
    assert cliente.get("/api/v1/salud-protegida").status_code == 200
    cliente.post("/api/v1/ingreso/salir")
    assert cliente.get("/api/v1/salud-protegida").status_code == 401


def test_con_identidad_real_se_ignoran_las_cabeceras_simuladas(entorno):
    _, app = entorno
    cliente = TestClient(app, headers={"X-Perfil-Simulado": "SUPERADMIN"})
    assert cliente.get("/api/v1/salud-protegida").status_code == 401
    assert cliente.get("/api/v1/usuarios").status_code == 401


def test_primer_ingreso_obliga_a_cambiar_la_clave(entorno):
    servicio, app = entorno
    alta(servicio, "nuevo@enav.com", "MEDICO", cambiar=True)
    cliente = TestClient(app)
    assert entrar(cliente, "nuevo@enav.com").json()["debe_cambiar_clave"] is True
    assert cliente.get("/api/v1/salud-protegida").status_code == 403
    corta = cliente.post("/api/v1/ingreso/clave", json={"actual": CLAVE, "nueva": "corta"})
    assert corta.status_code == 400
    mal = cliente.post("/api/v1/ingreso/clave", json={"actual": "incorrecta-x", "nueva": "otra-clave-larga"})
    assert mal.status_code == 400
    ok = cliente.post("/api/v1/ingreso/clave", json={"actual": CLAVE, "nueva": "otra-clave-larga"})
    assert ok.status_code == 200 and ok.json()["debe_cambiar_clave"] is False
    assert cliente.get("/api/v1/salud-protegida").status_code == 200


def test_bloqueo_tras_varios_intentos_fallidos(entorno):
    servicio, app = entorno
    alta(servicio, "rrhh@enav.com", "RRHH")
    cliente = TestClient(app)
    for _ in range(5):
        assert entrar(cliente, "rrhh@enav.com", "equivocada-1").status_code == 401
    bloqueado = entrar(cliente, "rrhh@enav.com")
    assert bloqueado.status_code == 401 and "15 minutos" in bloqueado.json()["detail"]


def test_solo_el_superadministrador_gestiona_usuarios(entorno):
    servicio, app = entorno
    alta(servicio, "admin@enav.com", "SUPERADMIN")
    alta(servicio, "medica@enav.com", "MEDICO")
    medica = TestClient(app)
    entrar(medica, "medica@enav.com")
    assert medica.get("/api/v1/usuarios").status_code == 403
    assert medica.post("/api/v1/usuarios", json={
        "email": "x@enav.com", "nombre": "X", "perfil": "SUPERADMIN", "empresa": "ENAV",
        "clave_inicial": CLAVE,
    }).status_code == 403

    admin = TestClient(app)
    entrar(admin, "admin@enav.com")
    creado = admin.post("/api/v1/usuarios", json={
        "email": "compras@enav.com", "nombre": "Compras", "perfil": "COMPRAS", "empresa": "JUBIAR",
        "clave_inicial": CLAVE,
    })
    assert creado.status_code == 200 and creado.json()["debe_cambiar_clave"] is True
    repetido = admin.post("/api/v1/usuarios", json={
        "email": "compras@enav.com", "nombre": "Otro", "perfil": "COMPRAS", "empresa": "ENAV",
        "clave_inicial": CLAVE,
    })
    assert repetido.status_code == 400
    assert {u["email"] for u in admin.get("/api/v1/usuarios").json()} >= {"compras@enav.com"}
    assert any(e["accion"] == "ALTA_USUARIO" for e in admin.get("/api/v1/usuarios/accesos").json())


def test_desactivar_un_usuario_corta_su_sesion(entorno):
    servicio, app = entorno
    admin_u = alta(servicio, "admin@enav.com", "SUPERADMIN")
    medica_u = alta(servicio, "medica@enav.com", "MEDICO")
    medica = TestClient(app)
    entrar(medica, "medica@enav.com")
    assert medica.get("/api/v1/salud-protegida").status_code == 200
    admin = TestClient(app)
    entrar(admin, "admin@enav.com")
    cambios = {"nombre": "Nombre", "perfil": "MEDICO", "empresa": "ENAV", "activo": False}
    assert admin.put(f"/api/v1/usuarios/{medica_u.id}", json=cambios).status_code == 200
    assert medica.get("/api/v1/salud-protegida").status_code == 401
    assert entrar(medica, "medica@enav.com").status_code == 401
    propio = {"nombre": "Yo", "perfil": "SUPERADMIN", "empresa": "ENAV", "activo": False}
    assert admin.put(f"/api/v1/usuarios/{admin_u.id}", json=propio).status_code == 400


def test_la_base_no_guarda_claves_ni_tokens_en_claro(entorno, tmp_path):
    servicio, app = entorno
    alta(servicio, "medica@enav.com", "MEDICO")
    cliente = TestClient(app)
    entrar(cliente, "medica@enav.com")
    token = cliente.cookies.get(dependencias.COOKIE_SESION)
    contenido = (tmp_path / "u.sqlite3").read_bytes()
    assert CLAVE.encode() not in contenido and token.encode() not in contenido


def test_el_bloqueo_no_alcanza_a_quien_entra_desde_otro_equipo(entorno):
    servicio, _ = entorno
    alta(servicio, "rrhh@enav.com", "RRHH")
    for _ in range(5):
        with pytest.raises(IngresoInvalido):
            servicio.ingresar("rrhh@enav.com", "equivocada-1", origen="10.0.0.9")
    with pytest.raises(IngresoInvalido, match="15 minutos"):
        servicio.ingresar("rrhh@enav.com", CLAVE, origen="10.0.0.9")
    token, _ = servicio.ingresar("rrhh@enav.com", CLAVE, origen="10.0.0.7")
    assert token


def test_la_bitacora_no_guarda_texto_arbitrario_como_correo(entorno):
    servicio, _ = entorno
    with pytest.raises(IngresoInvalido):
        servicio.ingresar("<script>" + "x" * 500, "algo", origen="10.0.0.9")
    assert servicio.repositorio.eventos()[0]["actor"] == "(correo no válido)"
