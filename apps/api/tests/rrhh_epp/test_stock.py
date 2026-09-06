"""Stock por ítem: descuentos, mínimos, permisos y datos inválidos."""

import pytest

from suite_juviar.modulos.rrhh_epp.domain.modelos_mvp import (
    StockInsuficiente,
    StockInvalido,
)


def _entregar(contenedor, *, cantidad: int = 1, id_entrega: str | None = None):
    return contenedor.registrar_entrega.ejecutar(
        numero_legajo="1042",
        items=[{"codigo": "68", "item_codigo": "SIM-68-01", "cantidad": cantidad}],
        metodo_firma="TRAZO_TABLET",
        evidencia_firma="data:image/png;base64,AAAA",
        usuario_deposito="1210",
        id_entrega=id_entrega,
    )


def test_stock_simulado_declara_dueno_y_un_registro_por_item(contenedor):
    assert contenedor.stock.estado == "SIMULADO"
    assert contenedor.stock.dueno_dato == "Depósito"
    assert len(contenedor.stock.listar()) == 435


def test_entrega_descuenta_la_cantidad_del_item_concreto(contenedor):
    antes = contenedor.stock.obtener("SIM-68-01")
    assert antes is not None
    _entregar(contenedor, cantidad=2)
    despues = contenedor.stock.obtener("SIM-68-01")
    assert despues is not None
    assert despues.disponible == antes.disponible - 2


def test_idempotencia_no_descuenta_dos_veces(contenedor):
    identificador = "TABLET-STOCK-0001"
    primera = _entregar(contenedor, id_entrega=identificador)
    disponible = contenedor.stock.obtener("SIM-68-01").disponible  # type: ignore[union-attr]
    segunda = _entregar(contenedor, id_entrega=identificador)
    assert segunda == primera
    assert contenedor.stock.obtener("SIM-68-01").disponible == disponible  # type: ignore[union-attr]


def test_lineas_repetidas_no_permiten_superar_el_stock(contenedor):
    contenedor.stock.configurar("SIM-68-01", disponible=3, minimo=0)
    with pytest.raises(StockInsuficiente):
        contenedor.registrar_entrega.ejecutar(
            numero_legajo="1042",
            items=[
                {"codigo": "68", "item_codigo": "SIM-68-01", "cantidad": 2},
                {"codigo": "68", "item_codigo": "SIM-68-01", "cantidad": 2},
            ],
            metodo_firma="TRAZO_TABLET",
            evidencia_firma="data:image/png;base64,AAAA",
            usuario_deposito="1210",
        )
    assert contenedor.entregas.listar_por_legajo("1042") == []
    assert contenedor.stock.obtener("SIM-68-01").disponible == 3  # type: ignore[union-attr]


def test_al_llegar_al_minimo_crea_un_solo_aviso_para_compras(contenedor):
    contenedor.stock.configurar("SIM-68-01", disponible=21, minimo=20)
    _entregar(contenedor, id_entrega="TABLET-STOCK-0002")
    avisos = contenedor.stock.alertas_pendientes()
    assert len(avisos) == 1
    assert avisos[0]["item_codigo"] == "SIM-68-01"
    assert avisos[0]["disponible"] == 20
    assert avisos[0]["minimo"] == 20

    # Otra entrega no duplica el aviso pendiente del mismo ítem.
    _entregar(contenedor, id_entrega="TABLET-STOCK-0003")
    assert len(contenedor.stock.alertas_pendientes()) == 1


def test_sin_stock_rechaza_y_no_guarda_entrega(contenedor):
    contenedor.stock.configurar("SIM-68-01", disponible=0, minimo=0)
    with pytest.raises(StockInsuficiente):
        _entregar(contenedor)
    assert contenedor.entregas.listar_por_legajo("1042") == []


@pytest.mark.parametrize(
    ("disponible", "minimo"),
    [(-1, 0), (0, -1), (True, 0), (0, False)],
)
def test_rechaza_existencias_o_minimos_invalidos(contenedor, disponible, minimo):
    with pytest.raises(StockInvalido):
        contenedor.stock.configurar("SIM-68-01", disponible, minimo)


def test_rechaza_configurar_un_item_inexistente(contenedor):
    with pytest.raises(StockInvalido):
        contenedor.stock.configurar("", 10, 2)


def test_api_expone_stock_estado_y_alertas(cliente):
    estado = cliente.get("/estado").json()
    assert estado["estado_stock"] == "SIMULADO"
    assert estado["dueno_stock"] == "Depósito"
    assert len(cliente.get("/stock").json()) == 435

    respuesta = cliente.put(
        "/stock/SIM-68-01",
        json={"disponible": 21, "minimo": 20},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "CONFIGURADO_DEPOSITO"


@pytest.mark.parametrize(
    "cuerpo",
    [
        {},
        {"disponible": None, "minimo": 1},
        {"disponible": 1, "minimo": None},
        {"disponible": -1, "minimo": 1},
        {"disponible": 1, "minimo": -1},
    ],
)
def test_api_rechaza_stock_vacio_nulo_o_negativo(cliente, cuerpo):
    respuesta = cliente.put("/stock/SIM-68-01", json=cuerpo)
    assert respuesta.status_code == 422


def test_perfiles_ajenos_no_pueden_ver_ni_configurar_stock(cliente):
    cabecera = {"X-Legajo-Usuario": "1501"}
    assert cliente.get("/stock", headers=cabecera).status_code == 403
    assert cliente.get("/stock/alertas", headers=cabecera).status_code == 403
    respuesta = cliente.put(
        "/stock/SIM-68-01",
        headers=cabecera,
        json={"disponible": 21, "minimo": 20},
    )
    assert respuesta.status_code == 403
