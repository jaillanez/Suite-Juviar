from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from suite_juviar.modulos.rrhh_epp.api.mvp import crear_router, tabla_de_errores
from suite_juviar.modulos.rrhh_epp.mvp import construir
from suite_juviar.plataforma.errores import registrar_manejadores


def test_epp_comparte_mapa_y_formato_de_error(tmp_path):
    app = FastAPI()
    contenedor = construir(entorno="prueba", ruta_base=str(tmp_path / "epp.sqlite3"))
    app.include_router(crear_router(contenedor), prefix="/api/v1/rrhh-epp")
    registrar_manejadores(app, tabla_de_errores())

    caminos = app.openapi()["paths"]
    assert len([ruta for ruta in caminos if ruta.startswith("/api/v1/rrhh-epp/")]) >= 25
    respuesta = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/rrhh-epp/legajos/no-existe",
        headers={"X-Legajo-Usuario": "1210", "X-Perfil-Simulado": "DEPOSITO"},
    )
    assert respuesta.status_code == 404
    assert set(respuesta.json()) == {"detail"}


def test_ningun_modulo_queda_montado_como_subaplicacion(monkeypatch):
    monkeypatch.setenv("SJ_HMAC_DATOS_PERSONALES", "h" * 32)
    monkeypatch.setenv("SJ_CLAVE_CIFRADO_DATOS_PERSONALES", "c" * 32)
    monkeypatch.setenv("SJ_ENTORNO", "prueba")
    from suite_juviar.main import app

    montados = [ruta.path for ruta in app.routes if isinstance(ruta, Mount)]
    assert not [ruta for ruta in montados if ruta.startswith("/api/v1/")]
    caminos = app.openapi()["paths"]
    for prefijo in (
        "rrhh-epp", "legajo", "salud", "turnos", "seleccion",
        "capacitaciones", "epp-analitica",
    ):
        assert any(ruta.startswith(f"/api/v1/{prefijo}") for ruta in caminos), prefijo
