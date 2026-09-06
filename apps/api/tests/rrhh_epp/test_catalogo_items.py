from datetime import date

import pytest


def test_catalogo_simulado_declara_dueno_estado_y_tres_items_por_elemento(contenedor):
    assert contenedor.catalogo.estado_items == "SIMULADO"
    assert contenedor.catalogo.dueno_items == "Higiene y Seguridad"
    elementos = contenedor.catalogo.listar_elementos()
    assert len(elementos) == 145
    assert sum(len(contenedor.catalogo.items_de(e.codigo)) for e in elementos) == 435
    assert all(len(contenedor.catalogo.items_de(e.codigo)) == 3 for e in elementos)


def test_la_ficha_expone_items_filtrados_y_su_estado(cliente):
    respuesta = cliente.get("/legajos/1077")
    assert respuesta.status_code == 200
    elemento = next(e for e in respuesta.json()["epp_requerido"] if e["codigo"] == "69")
    assert [i["codigo_interno"] for i in elemento["items"]] == [
        "SIM-69-01",
        "SIM-69-02",
        "SIM-69-03",
    ]
    assert {i["estado"] for i in elemento["items"]} == {"SIMULADO"}


def test_una_entrega_responde_que_item_concreto_recibio_el_legajo(contenedor):
    entrega = contenedor.registrar_entrega.ejecutar(
        numero_legajo="1077",
        items=[{"codigo": "69", "item_codigo": "SIM-69-02", "cantidad": 1}],
        metodo_firma="TRAZO_TABLET",
        evidencia_firma="data:image/png;base64,AAAA",
        usuario_deposito="1210",
        fecha=date(2026, 3, 12),
    )
    guardada = contenedor.entregas.obtener(entrega.id)
    assert guardada is not None
    assert guardada.legajo.legajo == "1077"
    assert guardada.fecha_entrega == date(2026, 3, 12)
    assert guardada.lineas[0].item_codigo == "SIM-69-02"
    assert guardada.lineas[0].marca == "DPS"
    assert guardada.lineas[0].tipo_modelo == "Guantes de Nitrilo Azul (Largo Cod.11356)"


@pytest.mark.parametrize("valor", ["", None])
def test_api_rechaza_item_vacio_o_nulo(cliente, valor):
    respuesta = cliente.post("/entregas", json={
        "legajo": "1103",
        "items": [{"codigo": "62", "item_codigo": valor, "cantidad": 1}],
        "evidencia_firma": "data:image/png;base64,AAAA",
    })
    assert respuesta.status_code == 422
