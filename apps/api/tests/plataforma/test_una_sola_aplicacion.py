import ast
import pathlib
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from suite_juviar.modulos.rrhh_epp.api.mvp import crear_router, tabla_de_errores
from suite_juviar.modulos.rrhh_epp.mvp import construir
from suite_juviar.plataforma.errores import registrar_manejadores

RAIZ_FUENTE = pathlib.Path(__file__).resolve().parents[2] / "src" / "suite_juviar"
VARIABLES_AJENAS = re.compile(r"NEXUS|ORACLE|DMZ", re.IGNORECASE)
NOMBRE_DE_CONEXION = re.compile(r"^[A-Z_]*(?:DSN|DATABASE_URL)[A-Z_]*$")


def _lecturas_del_entorno(arbol) -> list[tuple[int, str]]:
    """Detecta os.getenv, os.environ[...] y os.environ.get."""

    def es_environ(nodo) -> bool:
        return (isinstance(nodo, ast.Attribute) and nodo.attr == "environ") or (
            isinstance(nodo, ast.Name) and nodo.id == "environ"
        )

    def literal(argumentos) -> str | None:
        if argumentos and isinstance(argumentos[0], ast.Constant):
            valor = argumentos[0].value
            return valor if isinstance(valor, str) else None
        return None

    hallazgos: list[tuple[int, str]] = []
    for nodo in ast.walk(arbol):
        nombre = None
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
            if nodo.func.attr == "getenv" or (
                nodo.func.attr == "get" and es_environ(nodo.func.value)
            ):
                nombre = literal(nodo.args)
        elif isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name):
            if nodo.func.id == "getenv":
                nombre = literal(nodo.args)
        elif (
            isinstance(nodo, ast.Subscript)
            and es_environ(nodo.value)
            and isinstance(nodo.slice, ast.Constant)
            and isinstance(nodo.slice.value, str)
        ):
            nombre = nodo.slice.value
        if nombre:
            hallazgos.append((nodo.lineno, nombre))
    return hallazgos


def test_el_detector_reconoce_las_tres_formas_de_leer_el_entorno():
    fuente = (
        'import os\n'
        'a = os.getenv("SJ_UNO_DSN")\n'
        'b = os.environ["SJ_DOS_DSN"]\n'
        'c = os.environ.get("SJ_TRES_DSN", "").strip()\n'
    )
    encontradas = {nombre for _, nombre in _lecturas_del_entorno(ast.parse(fuente))}
    assert encontradas == {"SJ_UNO_DSN", "SJ_DOS_DSN", "SJ_TRES_DSN"}


def test_la_api_resuelve_su_conexion_en_un_solo_lugar():
    """Una conexión por proceso; recepción conserva su rol y unidad separados."""
    permitidos = {
        RAIZ_FUENTE / "plataforma" / "db" / "dsn.py",
        RAIZ_FUENTE / "config.py",
        RAIZ_FUENTE / "modulos" / "recepcion" / "integracion_oracle" / "config.py",
    }
    culpables = []
    for archivo in RAIZ_FUENTE.rglob("*.py"):
        if archivo in permitidos or "__pycache__" in archivo.parts:
            continue
        arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
        for numero, variable in _lecturas_del_entorno(arbol):
            if NOMBRE_DE_CONEXION.match(variable) and not VARIABLES_AJENAS.search(variable):
                culpables.append(f"{archivo.relative_to(RAIZ_FUENTE)}:{numero} {variable}")
    assert not culpables, culpables


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
