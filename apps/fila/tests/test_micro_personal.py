"""«Llegó el micro» en la consola de la guardia (infra/042)."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from fila_app import main
from fila_app.guardias import Sesion
from fila_app.web import guardia


class RepoFalso:
    def __init__(self):
        self.avisos = []

    def avisar_micro(self, recorrido_id, sede, actor):
        if self.avisos and self.avisos[-1][0] == recorrido_id:
            raise ValueError("ya se avisó la llegada de ese micro a las 07:02")
        self.avisos.append((recorrido_id, sede, actor))
        return {"aviso_id": 1, "recorrido": "Rawson", "destinatarios": 12}


def _cliente(sede_sesion="chimbas"):
    repo = RepoFalso()
    sesion = Sesion("mgomez", sede_sesion, datetime.now(UTC) + timedelta(hours=1))
    main.app.dependency_overrides[main.repo_guardia] = lambda: repo
    main.app.dependency_overrides[main.autenticar_guardia] = lambda: sesion
    return TestClient(main.app), repo


def teardown_function():
    main.app.dependency_overrides.clear()


def test_la_guardia_avisa_y_un_segundo_toque_no_vuelve_a_avisar():
    cliente, repo = _cliente()
    r = cliente.post("/api/guardia/chimbas/micro/4/llego")
    assert r.status_code == 200 and r.json()["destinatarios"] == 12
    assert repo.avisos == [(4, "chimbas", "guardia:mgomez")]
    doble = cliente.post("/api/guardia/chimbas/micro/4/llego")
    assert doble.status_code == 409 and "ya se avisó" in doble.json()["detail"]
    assert len(repo.avisos) == 1


def test_la_guardia_de_otra_bodega_no_puede_avisar():
    cliente, repo = _cliente("lavalle")
    assert cliente.post("/api/guardia/chimbas/micro/4/llego").status_code == 403
    assert repo.avisos == []


def test_la_consola_tiene_el_boton_y_elige_el_recorrido():
    html = guardia("chimbas")
    assert 'id="llegoMicro"' in html and "Llegó el micro" in html
    assert "¿De qué recorrido llegó el micro?" in html and "/micro/'+r+'/llego'" in html
