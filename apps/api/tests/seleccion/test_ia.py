import base64
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from suite_juviar.modulos.seleccion.api.app import crear_app
from suite_juviar.modulos.seleccion.infrastructure import ia_deepseek
from suite_juviar.modulos.seleccion.infrastructure.perfiles_yaml import CriteriosPerfilYAML

RAIZ = Path(__file__).resolve().parents[2] / "src" / "suite_juviar" / "modulos" / "seleccion" / "data"
RRHH = {"X-Perfil-Simulado": "RRHH"}


def cliente(entorno="prueba"):
    base = str(Path(tempfile.mkdtemp()) / "modulos.sqlite3")
    return TestClient(crear_app(CriteriosPerfilYAML(RAIZ / "criterios_perfil.yaml"), entorno, ruta_base=base))


def subir(c, nombre, contenido=b"imagen"):
    r = c.post("/cvs/lote", headers=RRHH, json={"archivos": [
        {"nombre": nombre, "contenido_base64": base64.b64encode(contenido).decode()}]})
    return r.json()["incorporados"][0]


def test_lee_cv_y_busca_candidatos_con_un_pedido(monkeypatch):
    monkeypatch.setenv("SJ_IA_DEEPSEEK_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(ia_deepseek, "leer_cv", lambda nombre, contenido, texto: {
        "nombre_completo": "Ana Pérez", "localidad": "Caucete", "oficios": ["capataz"], "resumen": "Capataz."})
    pedidos = []

    def buscar(pedido, fichas):
        pedidos.append((pedido, set(fichas)))
        return [{"id": cv_id, "encaje": "ALTO", "motivos": ["capataz"], "faltan": []} for cv_id in fichas]

    monkeypatch.setattr(ia_deepseek, "buscar_candidatos", buscar)
    c = cliente()
    leido = subir(c, "ana.png", b"uno")
    subir(c, "luis.png", b"dos")
    assert c.get("/ia/estado", headers=RRHH).json() == {"disponible": True, "total": 2, "leidos": 0}
    assert c.post(f"/cvs/{leido}/leer-ia", headers=RRHH).json()["nombre_completo"] == "Ana Pérez"
    resultado = c.post("/ia/buscar", headers=RRHH, json={"pedido": "Capataz de finca en Caucete"}).json()
    assert resultado["sin_leer"] == 1
    assert [x["nombre"] for x in resultado["candidatos"]] == ["Ana Pérez"]
    assert pedidos == [("Capataz de finca en Caucete", {leido})]


def test_sin_clave_o_sin_permiso_no_se_usa_la_ia(monkeypatch):
    monkeypatch.delenv("SJ_IA_DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("SJ_SALUD_IA_API_KEY", raising=False)
    c = cliente()
    cv = subir(c, "ana.png")
    assert c.post(f"/cvs/{cv}/leer-ia", headers=RRHH).status_code == 503
    assert c.post("/ia/buscar", headers={"X-Perfil-Simulado": "MEDICO"},
                  json={"pedido": "Capataz de finca"}).status_code == 403
