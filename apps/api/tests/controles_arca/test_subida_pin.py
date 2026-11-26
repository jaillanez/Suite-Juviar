"""Subir facturas con link personal + PIN: ingreso, bloqueos, sesión acotada y administración."""

import sqlite3
from datetime import timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from suite_juviar.modulos.controles_arca.api.app import crear_router
from suite_juviar.plataforma.identidad.api.dependencias import (
    PERMISOS_POR_PERFIL,
    configurar_ingreso,
    configurar_subida,
    exigir_permiso,
)
from suite_juviar.plataforma.identidad.api.ingreso import router as ingreso_router
from suite_juviar.plataforma.identidad.api.subida import router as subida_router
from suite_juviar.plataforma.identidad.application.ingreso import ServicioIngreso
from suite_juviar.plataforma.identidad.application.subida_pin import ServicioSubidaPin
from suite_juviar.plataforma.identidad.domain.subida_pin import (
    IngresoSubidaInvalido,
    PersonaSubida,
)
from suite_juviar.plataforma.identidad.infrastructure.subida_sqlite import SubidaPinSQLite
from suite_juviar.plataforma.identidad.infrastructure.usuarios_sqlite import UsuariosSQLite

from .test_controles_arca import Reloj
from .test_factura_celular import FOTO, datos_qr, preparado, url_qr

SUBIR = {"X-Ingreso-Subida": "1"}


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    monkeypatch.setenv("SJ_COOKIE_SEGURA", "0")
    monkeypatch.delenv("SJ_IDENTIDAD_REAL", raising=False)
    reloj = Reloj()
    ruta = tmp_path / "usuarios.sqlite3"
    subida = ServicioSubidaPin(SubidaPinSQLite(ruta), reloj=reloj)
    configurar_subida(subida)
    s, conector = preparado()
    s._reloj = reloj
    app = FastAPI()
    app.include_router(crear_router(s, "prueba"), prefix="/controles-arca")
    app.include_router(subida_router)

    @app.get("/otro-modulo", dependencies=[Depends(exigir_permiso("suite.acceder"))])
    def otro():
        return {"ok": True}

    yield {"subida": subida, "s": s, "reloj": reloj, "app": app, "ruta": ruta, "conector": conector}
    configurar_subida(None)


def admin(app, perfil="SUPERADMIN"):
    return TestClient(app, headers={"X-Perfil-Simulado": perfil, "X-Actor-Simulado": perfil.lower()})


def alta(app, nombre="Juan Pérez", empresas=("ENAV",), pin=None):
    r = admin(app).post("/controles-arca/subida-pin/personas",
                        json={"nombre": nombre, "empresas": list(empresas), **({"pin": pin} if pin else {})})
    assert r.status_code == 201, r.text
    return r.json()


def celular(app):
    return TestClient(app, headers=SUBIR)


def entrar(cliente, codigo, pin):
    return cliente.post("/subir/ingreso", json={"codigo": codigo, "pin": pin})


def otro_pin(pin):
    return f"{(int(pin) + 1) % 1000:03d}"


# --- Ingreso -------------------------------------------------------------------

def test_pin_correcto_entra_y_el_celular_queda_recordado(entorno):
    nuevo = alta(entorno["app"], pin="482")
    assert nuevo["pin"] == "482" and len(nuevo["codigo"].split(".")[1]) >= 32  # 192 bits en base64
    c = celular(entorno["app"])
    assert c.get("/subir/yo").status_code == 401
    r = entrar(c, nuevo["codigo"], "482")
    assert r.status_code == 200 and r.json() == {"nombre": "Juan Pérez", "empresas": ["ENAV"]}
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and f"max-age={30 * 24 * 3600}" in cookie
    assert c.get("/subir/yo").json()["nombre"] == "Juan Pérez"
    assert c.get("/controles-arca/celular/catalogo").json()["empresas"] == ["ENAV"]
    c.post("/subir/salir")
    assert c.get("/subir/yo").status_code == 401


def test_pin_incorrecto_avisa_cuantos_intentos_quedan_y_bloquea_a_los_5_por_15_minutos(entorno):
    nuevo = alta(entorno["app"], pin="123")
    c = celular(entorno["app"])
    for quedan in (4, 3, 2, 1):
        r = entrar(c, nuevo["codigo"], "999")
        assert r.status_code == 401 and f"{quedan} intento" in r.json()["detail"]
    r = entrar(c, nuevo["codigo"], "999")
    assert r.status_code == 429 and "hasta las 10:15" in r.json()["detail"]  # 13:00 UTC = 10:00 en Argentina
    # Bloqueado: ni el PIN correcto entra, y lo cuenta el servidor (otro celular, mismo resultado).
    assert entrar(celular(entorno["app"]), nuevo["codigo"], "123").status_code == 429
    entorno["reloj"].ahora += timedelta(minutes=14, seconds=59)
    assert entrar(c, nuevo["codigo"], "123").status_code == 429
    entorno["reloj"].ahora += timedelta(seconds=2)
    assert entrar(c, nuevo["codigo"], "123").status_code == 200
    persona = entorno["subida"].listar()[0]
    assert (persona.fallos_seguidos, persona.fallos_acumulados, persona.bloqueado_hasta) == (0, 0, None)


def test_muchos_fallos_sin_un_ingreso_bueno_desactivan_el_link_hasta_regenerarlo(entorno):
    app, reloj = entorno["app"], entorno["reloj"]
    nuevo = alta(app, pin="321")
    c = celular(app)
    for vuelta in range(4):
        for _ in range(5):
            r = entrar(c, nuevo["codigo"], "000")
        reloj.ahora += timedelta(minutes=16)
    assert r.status_code == 403 and "desactivado" in r.json()["detail"]
    assert entrar(c, nuevo["codigo"], "321").status_code == 403
    lista = admin(app).get("/controles-arca/subida-pin/personas").json()
    assert lista[0]["estado"] == "link_desactivado"
    regenerado = admin(app).post(f"/controles-arca/subida-pin/personas/{lista[0]['id']}/link").json()
    assert regenerado["codigo"] != nuevo["codigo"]
    assert entrar(c, nuevo["codigo"], "321").status_code == 401  # el link viejo ya no sirve
    assert entrar(c, regenerado["codigo"], "321").status_code == 200


def test_link_inexistente_o_falso_no_revela_nada(entorno):
    nuevo = alta(entorno["app"], pin="555")
    persona_id, secreto = nuevo["codigo"].split(".")
    c = celular(entorno["app"])
    respuestas = [entrar(c, codigo, pin) for codigo, pin in (
        ("00000000." + secreto, "555"), (f"{persona_id}.otro-secreto", "555"), (persona_id, "555"),
        ("cualquier-cosa", "555"), (f"{persona_id}.{secreto[:-1]}", "555"))]
    assert {(r.status_code, r.json()["detail"]) for r in respuestas} == {
        (401, "Este link no sirve para entrar. Pedile uno nuevo a Administración.")}
    # Los intentos con link falso no cuentan contra la persona.
    assert entorno["subida"].listar()[0].fallos_acumulados == 0
    # Una persona desactivada responde igual que un link que no existe.
    admin(entorno["app"]).post(f"/controles-arca/subida-pin/personas/{persona_id}/desactivar")
    r = entrar(c, nuevo["codigo"], "555")
    assert (r.status_code, r.json()["detail"]) == (401, respuestas[0].json()["detail"])


def test_muchos_links_falsos_desde_un_equipo_lo_frenan(entorno):
    c = celular(entorno["app"])
    for _ in range(30):
        entrar(c, "00000000.x", "111")
    assert entrar(c, "00000000.x", "111").status_code == 429


def test_pin_mal_formado_no_llega_al_servicio(entorno):
    nuevo = alta(entorno["app"])
    c = celular(entorno["app"])
    for pin in ("12", "1234", "abc", "１２３"):
        assert entrar(c, nuevo["codigo"], pin).status_code == 422
    assert entorno["subida"].listar()[0].fallos_acumulados == 0


# --- Sesión acotada ---------------------------------------------------------------

def test_la_sesion_pin_solo_pasa_los_endpoints_del_celular(entorno):
    app = entorno["app"]
    nuevo = alta(app, pin="777")
    c = celular(app)
    entrar(c, nuevo["codigo"], "777")
    r = c.post("/controles-arca/celular/qr", json={"qr": url_qr(), "foto_base64": FOTO})
    assert r.status_code == 200, r.text
    factura = r.json()["factura"]
    assert factura["cargada_por"] == f"Juan Pérez (PIN {nuevo['persona']['id']})"
    assert c.get(f"/controles-arca/celular/facturas/{factura['id']}").status_code == 200
    assert c.get(f"/controles-arca/celular/facturas/{factura['id']}/foto").status_code == 200
    prohibidas = [
        ("get", "/controles-arca/catalogo"), ("get", "/controles-arca/facturas"),
        ("get", f"/controles-arca/facturas/{factura['id']}"), ("get", f"/controles-arca/facturas/{factura['id']}/foto"),
        ("post", f"/controles-arca/facturas/{factura['id']}/controles"), ("get", "/controles-arca/parametros"),
        ("get", "/controles-arca/certificado"), ("get", "/controles-arca/subida-pin/personas"),
        ("post", "/controles-arca/padrones/rg18/actualizar"), ("get", "/otro-modulo"),
    ]
    for metodo, ruta in prohibidas:
        assert getattr(c, metodo)(ruta).status_code == 403, ruta
    # Aunque mande cabeceras de perfil simulado, con la cabecera de subida manda la cookie de PIN.
    for metodo, ruta in prohibidas:
        assert getattr(c, metodo)(ruta, headers={"X-Perfil-Simulado": "SUPERADMIN"}).status_code == 403, ruta
    # Sin la cookie de PIN, la cabecera de subida no da ninguna sesión.
    assert TestClient(app, headers={**SUBIR, "X-Perfil-Simulado": "SUPERADMIN"}).get(
        "/controles-arca/celular/catalogo").status_code == 401


def test_con_pin_solo_ve_sus_facturas_y_solo_carga_en_sus_empresas(entorno):
    app, s = entorno["app"], entorno["s"]
    # Una factura que cargó Administración desde Gestión.
    gestion = admin(app, "ADMINISTRACION")
    ajena = gestion.post("/controles-arca/celular/qr", json={"qr": url_qr(), "foto_base64": FOTO}).json()["factura"]
    nuevo = alta(app, pin="246")
    c = celular(app)
    entrar(c, nuevo["codigo"], "246")
    r = c.post("/controles-arca/celular/qr", json={"qr": url_qr(), "foto_base64": FOTO}).json()
    assert r["ajena"] is True and r["ya_cargada"] is True
    assert set(r["factura"]) == {"comprobante", "empresa", "cuit_emisor", "fecha", "importe_total", "moneda",
                                 "importe_texto"}
    assert "administracion" not in str(r) and ajena["id"] not in str(r)
    assert c.get(f"/controles-arca/celular/facturas/{ajena['id']}").status_code == 404
    assert c.get(f"/controles-arca/celular/facturas/{ajena['id']}/foto").status_code == 404
    # JUBIAR no es de sus empresas: el QR dice que el receptor es ENAV, así que otra factura a JUBIAR no se carga.
    s.guardar_parametros({**s.vista_parametros(), "cuit_empresas": {"ENAV": "30546689979", "JUBIAR": "30500010912"}},
                         "admin")
    a_jubiar = c.post("/controles-arca/celular/qr", json={
        "qr": url_qr(datos_qr(nroCmp=9, nroDocRec=30500010912)), "foto_base64": FOTO})
    assert a_jubiar.status_code == 403 and "JUBIAR" in a_jubiar.json()["detail"]
    elegida = c.post("/controles-arca/celular/qr", json={
        "qr": url_qr(datos_qr(nroCmp=10, nroDocRec=30712345671)), "foto_base64": FOTO, "empresa": "JUBIAR"})
    assert elegida.status_code == 403
    assert len(s.repo.facturas) == 1
    # La suya sí la ve completa.
    propia = c.post("/controles-arca/celular/qr", json={"qr": url_qr(datos_qr(nroCmp=11)), "foto_base64": FOTO}).json()
    assert "ajena" not in propia and propia["factura"]["controles"]
    # Y Gestión con «operar» sigue usando el celular como siempre, sin recortes.
    otra_vez = gestion.post("/controles-arca/celular/qr", json={"qr": url_qr(datos_qr(nroCmp=11)), "foto_base64": FOTO})
    assert otra_vez.json()["factura"]["cargada_por"].startswith("Juan Pérez (PIN")
    assert gestion.get("/controles-arca/celular/catalogo").json()["empresas"] == ["ENAV", "JUBIAR"]


def test_desactivar_o_regenerar_revoca_las_sesiones(entorno):
    app = entorno["app"]
    nuevo = alta(app, pin="135")
    pid = nuevo["persona"]["id"]
    c = celular(app)

    def sigue():
        return c.get("/controles-arca/celular/catalogo").status_code == 200

    entrar(c, nuevo["codigo"], "135")
    assert sigue()
    pin = admin(app).post(f"/controles-arca/subida-pin/personas/{pid}/pin", json={}).json()["pin"]
    assert len(pin) == 3 and pin.isdigit() and not sigue()
    if pin != "135":
        assert entrar(c, nuevo["codigo"], "135").status_code == 401
    entrar(c, nuevo["codigo"], pin)
    assert sigue()
    codigo = admin(app).post(f"/controles-arca/subida-pin/personas/{pid}/link").json()["codigo"]
    assert not sigue()
    entrar(c, codigo, pin)
    assert sigue()
    admin(app).post(f"/controles-arca/subida-pin/personas/{pid}/desactivar")
    assert not sigue()
    assert entrar(c, codigo, pin).status_code == 401


def test_la_sesion_vence_a_los_30_dias(entorno):
    nuevo = alta(entorno["app"], pin="864")
    c = celular(entorno["app"])
    entrar(c, nuevo["codigo"], "864")
    entorno["reloj"].ahora += timedelta(days=29, hours=23)
    assert c.get("/subir/yo").status_code == 200
    entorno["reloj"].ahora += timedelta(hours=2)
    assert c.get("/subir/yo").status_code == 401
    assert c.get("/controles-arca/celular/catalogo").status_code == 401


def test_nunca_se_guarda_el_pin_ni_el_link_en_claro(entorno):
    nuevo = alta(entorno["app"], pin="909")
    c = celular(entorno["app"])
    token = entrar(c, nuevo["codigo"], "909").cookies.get("sj_subida")
    secreto = nuevo["codigo"].split(".")[1]
    contenido = entorno["ruta"].read_bytes()
    for wal in entorno["ruta"].parent.glob("*-wal"):
        contenido += wal.read_bytes()
    assert secreto.encode() not in contenido and token.encode() not in contenido
    with sqlite3.connect(entorno["ruta"]) as cn:
        pin, guardado = cn.execute("SELECT pin, secreto FROM subida_persona").fetchone()
    assert pin.startswith("scrypt$") and guardado.startswith("scrypt$")
    assert len(pin.split("$")) == 6 and len(guardado.split("$")) == 6
    # Con sal: el mismo PIN para otra persona da otro resumen.
    alta(entorno["app"], nombre="Otra", pin="909")
    with sqlite3.connect(entorno["ruta"]) as cn:
        pines = [f[0] for f in cn.execute("SELECT pin FROM subida_persona")]
    assert len(set(pines)) == 2
    # La lista de Administración no muestra ni el PIN ni el link.
    lista = admin(entorno["app"]).get("/controles-arca/subida-pin/personas").text
    assert secreto not in lista and "scrypt" not in lista


# --- Administración ---------------------------------------------------------------

def test_administracion_solo_con_parametros_gestionar_y_queda_auditada(entorno):
    app = entorno["app"]
    for perfil in ("ADMINISTRACION", "COMPRAS", "RRHH"):
        assert admin(app, perfil).get("/controles-arca/subida-pin/personas").status_code == 403
        assert admin(app, perfil).post("/controles-arca/subida-pin/personas",
                                       json={"nombre": "X", "empresas": ["ENAV"]}).status_code == 403
    assert admin(app).post("/controles-arca/subida-pin/personas",
                           json={"nombre": "X", "empresas": []}).status_code == 422
    assert admin(app).post("/controles-arca/subida-pin/personas",
                           json={"nombre": "X", "empresas": ["ENAV"], "pin": "12"}).status_code == 422
    assert admin(app).post("/controles-arca/subida-pin/personas/no-existe/link").status_code == 404
    nuevo = alta(app, empresas=("ENAV", "JUBIAR"))
    c = celular(app)
    entrar(c, nuevo["codigo"], nuevo["pin"])
    c.post("/controles-arca/celular/qr", json={"qr": url_qr(), "foto_base64": FOTO})
    entrar(c, nuevo["codigo"], otro_pin(nuevo["pin"]))
    entrar(c, nuevo["codigo"], otro_pin(nuevo["pin"]))
    entrar(c, nuevo["codigo"], otro_pin(nuevo["pin"]))
    entrar(c, nuevo["codigo"], otro_pin(nuevo["pin"]))
    entrar(c, nuevo["codigo"], otro_pin(nuevo["pin"]))
    fila = admin(app).get("/controles-arca/subida-pin/personas").json()[0]
    assert fila["facturas"] == 1 and fila["estado"] == "bloqueado" and fila["bloqueado_hasta"]
    assert fila["ultimo_ingreso"] and fila["empresas"] == ["ENAV", "JUBIAR"] and fila["creado_por"] == "superadmin"
    admin(app).post(f"/controles-arca/subida-pin/personas/{fila['id']}/desactivar")
    acciones = [e["accion"] for e in admin(app).get("/controles-arca/subida-pin/eventos").json()]
    for accion in ("ALTA_SUBIDA_PIN", "INGRESO_SUBIDA", "INGRESO_SUBIDA_FALLIDO", "BLOQUEO_SUBIDA",
                   "DESACTIVAR_SUBIDA_PIN"):
        assert accion in acciones
    eventos = admin(app).get("/controles-arca/subida-pin/eventos").json()
    alta_evento = next(e for e in eventos if e["accion"] == "ALTA_SUBIDA_PIN")
    assert alta_evento["actor"] == "superadmin" and alta_evento["momento"]


def test_con_identidad_real_la_cookie_de_pin_no_es_una_sesion_de_gestion(entorno, monkeypatch, tmp_path):
    monkeypatch.setenv("SJ_IDENTIDAD_REAL", "1")
    configurar_ingreso(ServicioIngreso(UsuariosSQLite(tmp_path / "u.sqlite3"), frozenset(PERMISOS_POR_PERFIL)))
    try:
        app = entorno["app"]
        app.include_router(ingreso_router)
        _, pin, codigo = entorno["subida"].alta("admin", "Ana", ["ENAV"])
        c = TestClient(app)
        assert c.post("/subir/ingreso", json={"codigo": codigo, "pin": pin}).status_code == 200
        # Sin la cabecera de /subir, la cookie de PIN no sirve para nada de Gestión.
        assert c.get("/controles-arca/celular/catalogo").status_code == 401
        assert c.get("/ingreso/yo").status_code == 401
        assert c.get("/controles-arca/celular/catalogo", headers=SUBIR).status_code == 200
    finally:
        configurar_ingreso(None)


def test_servicio_con_reloj_inyectable():
    from suite_juviar.plataforma.identidad.application import subida_pin

    class Repo:
        def __init__(self):
            self.personas, self.sesiones, self.eventos_ = {}, {}, []

        def crear(self, persona, pin, secreto):
            self.personas[persona.id] = [persona, pin, secreto]

        def obtener(self, pid):
            fila = self.personas.get(pid)
            return tuple(fila) if fila else None

        def listar(self):
            return [f[0] for f in self.personas.values()]

        def actualizar(self, persona: PersonaSubida):
            self.personas[persona.id][0] = persona

        def cambiar_pin(self, pid, pin):
            self.personas[pid][1] = pin

        def cambiar_secreto(self, pid, secreto):
            self.personas[pid][2] = secreto

        def guardar_sesion(self, token, sesion):
            self.sesiones[token] = sesion

        def obtener_sesion(self, token):
            return self.sesiones.get(token)

        def borrar_sesion(self, token):
            self.sesiones.pop(token, None)

        def borrar_sesiones_de(self, pid):
            self.sesiones = {t: x for t, x in self.sesiones.items() if x.persona_id != pid}

        def registrar_evento(self, actor, accion, detalle=""):
            self.eventos_.append(accion)

        def eventos(self, limite=200):
            return []

    reloj = Reloj()
    servicio = subida_pin.ServicioSubidaPin(Repo(), reloj=reloj)
    persona, pin, codigo = servicio.alta("admin", "  Ana   María ", ["jubiar"])
    assert persona.nombre == "Ana María" and persona.empresas == ("JUBIAR",)
    with pytest.raises(IngresoSubidaInvalido) as error:
        servicio.ingresar(codigo, otro_pin(pin))
    assert error.value.motivo == "pin" and error.value.intentos_restantes == 4
    token, _ = servicio.ingresar(codigo, pin)
    assert servicio.resolver(token) is not None
    reloj.ahora += timedelta(days=30)
    assert servicio.resolver(token) is None
