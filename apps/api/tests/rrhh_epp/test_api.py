from datetime import UTC, datetime


def test_estado_avisa_que_es_simulado(cliente):
    d = cliente.get("/estado").json()
    assert d["modo_simulado"] is True
    assert d["fuente_legajos"] == "SIMULADA"
    assert d["estado_matriz_epp"] == "PROPUESTA_SIN_VALIDAR"


def test_sesion_asigna_el_perfil_segun_el_usuario(cliente):
    r = cliente.get("/sesion")
    assert r.status_code == 200
    assert r.json()["legajo"] == "1210"
    assert r.json()["perfil"] == "deposito"


def test_sin_identidad_declarada_rechaza(cliente):
    r = cliente.get("/sesion", headers={"X-Legajo-Usuario": ""})
    assert r.status_code == 401


def test_un_sector_sin_perfil_muestra_error_sin_otorgar_permisos(cliente):
    r = cliente.get("/sesion", headers={"X-Legajo-Usuario": "1042"})
    assert r.status_code == 403
    assert "no tiene un perfil móvil habilitado" in r.json()["detail"]


def test_un_usuario_de_campo_no_puede_entregar_epp(cliente):
    cabecera = {"X-Legajo-Usuario": "1501"}
    assert cliente.get("/sesion", headers=cabecera).json()["perfil"] == "campo"
    assert cliente.get("/legajos?q=Quiroga", headers=cabecera).status_code == 403
    assert cliente.get("/matriz", headers=cabecera).status_code == 403


def test_un_usuario_de_bascula_no_puede_entregar_epp(cliente):
    cabecera = {"X-Legajo-Usuario": "1601"}
    assert cliente.get("/sesion", headers=cabecera).json()["perfil"] == "bascula"
    assert cliente.get("/legajos?q=Quiroga", headers=cabecera).status_code == 403
    assert cliente.get("/matriz", headers=cabecera).status_code == 403


def test_un_usuario_de_campo_no_puede_revisar_la_matriz(cliente):
    r = cliente.get("/matriz", headers={"X-Legajo-Usuario": "1501"})
    assert r.status_code == 403


def test_un_usuario_de_campo_no_puede_leer_alertas_del_catalogo(cliente):
    r = cliente.get("/alertas-catalogo", headers={"X-Legajo-Usuario": "1501"})
    assert r.status_code == 403


def test_el_cliente_no_puede_suplantar_al_operador(cliente):
    r = cliente.post("/entregas", json={
        "legajo": "1103",
        "items": [{"codigo": "62", "cantidad": 1}],
        "evidencia_firma": "data:image/png;base64,AAAA",
        "usuario_deposito": "otro-legajo",
    })
    assert r.status_code == 422


def test_la_bitacora_toma_la_identidad_declarada_no_el_cuerpo(cliente):
    r = cliente.post("/entregas", json={
        "legajo": "1103",
        "items": [{"codigo": "62", "cantidad": 1}],
        "evidencia_firma": "data:image/png;base64,AAAA",
    })
    assert r.status_code == 200
    assert cliente.get("/bitacora?n=1").json()[0]["usuario"] == "1210"


def test_identidad_declarada_rechaza_un_cliente_de_red(monkeypatch):
    from fastapi.testclient import TestClient

    from suite_juviar.modulos.rrhh_epp.api.mvp import crear_app
    from suite_juviar.modulos.rrhh_epp.mvp import construir

    monkeypatch.setenv("SJ_HABILITAR_IDENTIDAD_DECLARADA", "SI")
    contenedor = construir(entorno="desarrollo", fuente_legajos="yaml", ruta_base=":memory:")
    cliente_red = TestClient(
        crear_app(contenedor),
        base_url="http://192.168.1.20",
        client=("192.168.1.30", 50000),
        headers={"X-Legajo-Usuario": "1210"},
    )
    r = cliente_red.get("/sesion")
    assert r.status_code == 403
    assert "sólo se admite desde loopback" in r.json()["detail"]


def test_identidad_declarada_rechaza_origen_remoto_detras_de_proxy(monkeypatch):
    from fastapi.testclient import TestClient

    from suite_juviar.modulos.rrhh_epp.api.mvp import crear_app
    from suite_juviar.modulos.rrhh_epp.mvp import construir

    monkeypatch.setenv("SJ_HABILITAR_IDENTIDAD_DECLARADA", "SI")
    contenedor = construir(entorno="desarrollo", fuente_legajos="yaml", ruta_base=":memory:")
    cliente_proxy = TestClient(
        crear_app(contenedor),
        base_url="http://127.0.0.1:8000",
        client=("127.0.0.1", 50000),
        headers={"X-Legajo-Usuario": "1210"},
    )
    r = cliente_proxy.get(
        "/sesion",
        headers={
            "Origin": "http://192.168.1.20:3001",
            "X-Forwarded-For": "192.168.1.30",
        },
    )
    assert r.status_code == 403


def test_identidad_declarada_admite_loopback_cuando_fue_habilitada(monkeypatch):
    from fastapi.testclient import TestClient

    from suite_juviar.modulos.rrhh_epp.api.mvp import crear_app
    from suite_juviar.modulos.rrhh_epp.mvp import construir

    monkeypatch.setenv("SJ_HABILITAR_IDENTIDAD_DECLARADA", "SI")
    contenedor = construir(entorno="desarrollo", fuente_legajos="yaml", ruta_base=":memory:")
    cliente_local = TestClient(
        crear_app(contenedor),
        base_url="http://127.0.0.1:8000",
        client=("127.0.0.1", 50000),
        headers={"X-Legajo-Usuario": "1210"},
    )
    assert cliente_local.get("/sesion").status_code == 200


def test_ficha_trae_cabecera_y_epp_del_puesto(cliente):
    d = cliente.get("/legajos/1077").json()
    assert d["cabecera"]["nombre_completo"] == "Olivares, Marisa Beatriz"
    assert d["cabecera"]["puesto"] == "Operaria de Clarificación"
    codigos = {e["codigo"] for e in d["epp_requerido"]}
    assert {"8", "10", "69"} <= codigos
    origenes = {e["codigo"]: e["origen"] for e in d["epp_requerido"]}
    assert origenes["8"] == "BASE"
    assert origenes["69"] == "SECTOR"
    assert all(e["fundamento"] for e in d["epp_requerido"])


def test_legajo_inexistente_da_404(cliente):
    r = cliente.get("/legajos/999999")
    assert r.status_code == 404
    assert "no existe" in r.json()["error"]


def test_legajo_inactivo_da_400(cliente):
    r = cliente.get("/legajos/0988")
    assert r.status_code == 400


def test_entrega_completa_y_constancia(cliente):
    r = cliente.post("/entregas", json={
        "legajo": "1103",
        "items": [{"codigo": "62", "cantidad": 1}, {"codigo": "5", "cantidad": 1}],
        "metodo_firma": "TRAZO_TABLET",
        "evidencia_firma": "data:image/png;base64,AAAA",
    })
    assert r.status_code == 200, r.text
    entrega = r.json()
    assert entrega["items"] == 2
    assert entrega["firma_simulada"] is True

    constancia = cliente.get(f"/constancias/{entrega['id']}")
    assert constancia.status_code == 200
    assert "Funes, Héctor Daniel" in constancia.text
    assert "24880431" in constancia.text
    assert "Calzado de Seguridad" in constancia.text
    assert "Documento de prueba" in constancia.text
    assert "validez legal" in constancia.text


def test_la_segunda_consulta_muestra_la_entrega_anterior(cliente):
    cliente.post("/entregas", json={
        "legajo": "1210",
        "items": [{"codigo": "5", "cantidad": 1}],
        "evidencia_firma": "data:image/png;base64,AAAA",
    })
    d = cliente.get("/legajos/1210").json()
    calzado = next(e for e in d["epp_requerido"] if e["codigo"] == "5")
    assert calzado["ultima_entrega"] is not None
    assert len(d["historial"]) == 1


def test_constancia_inexistente_da_404(cliente):
    assert cliente.get("/constancias/NOEXISTE").status_code == 404


def test_pantalla_de_revision_de_matriz_es_solo_lectura(cliente):
    r = cliente.get("/matriz")
    assert r.status_code == 200
    assert "Propuesta sin validar" in r.text
    assert "Clarificación" in r.text and "Calderas" in r.text
    assert "a definir con HyS" in r.text
    assert "el catálogo declara" in r.text
    assert "27" in r.text
    assert "REFERENCIAL_INVESTIGADO" in r.text
    assert "Aprobar" not in r.text


def test_api_expone_alertas_sin_bloquear_entregas(cliente):
    r = cliente.get("/alertas-catalogo")
    assert r.status_code == 200
    assert r.json()["cantidad"] == 27
    assert r.json()["estado_vida_util"] == "REFERENCIAL_INVESTIGADO"

    entrega = cliente.post("/entregas", json={
        "legajo": "1103",
        "items": [{"codigo": "105", "cantidad": 1}],
        "evidencia_firma": "data:image/png;base64,AAAA",
    })
    assert entrega.status_code == 200


def test_reenviar_la_misma_entrega_genera_un_solo_registro(cliente):
    cuerpo = {
        "id_cliente": "tablet-20260906-0001",
        "legajo": "1103",
        "items": [{"codigo": "62", "cantidad": 1}],
        "metodo_firma": "TRAZO_TABLET",
        "evidencia_firma": "data:image/png;base64,AAAA",
        "entregada_en": "2026-09-06T13:45:12-03:00",
        "actor_declarado": "1210",
    }

    primera = cliente.post("/entregas", json=cuerpo)
    segunda = cliente.post("/entregas", json=cuerpo)

    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert primera.json()["id"] == segunda.json()["id"] == cuerpo["id_cliente"]
    ficha = cliente.get("/legajos/1103").json()
    assert [e["id"] for e in ficha["historial"]] == [cuerpo["id_cliente"]]
    eventos = cliente.get("/bitacora?n=10").json()
    assert [e["detalle"]["id_entrega"] for e in eventos] == [cuerpo["id_cliente"]]


def test_el_servidor_conserva_el_sello_real_de_la_tablet(cliente, contenedor):
    sello = datetime(2026, 9, 6, 16, 45, 12, tzinfo=UTC)
    r = cliente.post(
        "/entregas",
        json={
            "id_cliente": "tablet-20260906-0002",
            "legajo": "1103",
            "items": [{"codigo": "62", "cantidad": 1}],
            "evidencia_firma": "data:image/png;base64,AAAA",
            "entregada_en": sello.isoformat(),
            "actor_declarado": "1210",
        },
    )

    assert r.status_code == 200
    guardada = contenedor.entregas.obtener("tablet-20260906-0002")
    assert guardada is not None
    assert guardada.firma_trabajador.sello_tiempo == sello
