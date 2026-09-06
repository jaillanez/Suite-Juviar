from datetime import date

import pytest

from suite_juviar.modulos.rrhh_epp.domain.modelos_mvp import (
    CircuitoEntregaInvalido,
    MotivoReposicionInvalido,
)


def test_plan_programado_arma_personas_y_elementos_por_sector(contenedor):
    planes = contenedor.planificar_entregas.ejecutar(
        "VERANO",
        date(2026, 11, 2),
        "CLA",
    )
    assert [plan.trabajador.legajo for plan in planes] == ["1077"]
    assert {r.codigo for r in planes[0].requisitos} == {"8", "9", "10", "16"}
    assert all(r.frecuencia == "SEMESTRAL" for r in planes[0].requisitos)


def test_programada_y_espontanea_guardan_su_circuito(contenedor):
    programada = contenedor.registrar_entrega.ejecutar(
        numero_legajo="1077",
        items=[{"codigo": "8", "item_codigo": "SIM-8-01", "cantidad": 2}],
        metodo_firma="TRAZO_TABLET",
        evidencia_firma="firma",
        usuario_deposito="1210",
        circuito="PROGRAMADA",
        motivo="ENTREGA_ESTACIONAL",
    )
    espontanea = contenedor.registrar_entrega.ejecutar(
        numero_legajo="1077",
        items=[{"codigo": "69", "item_codigo": "SIM-69-01", "cantidad": 1}],
        metodo_firma="TRAZO_TABLET",
        evidencia_firma="firma",
        usuario_deposito="1210",
        circuito="ESPONTANEA",
        motivo="ROTURA",
    )
    assert contenedor.entregas.obtener(programada.id).motivo == "ENTREGA_ESTACIONAL"
    assert contenedor.entregas.obtener(espontanea.id).motivo == "ROTURA"


@pytest.mark.parametrize("circuito", ["", "MASIVA", None])
def test_rechaza_circuito_vacio_nulo_o_inventado(contenedor, circuito):
    with pytest.raises(CircuitoEntregaInvalido):
        contenedor.registrar_entrega.ejecutar(
            numero_legajo="1077",
            items=[{"codigo": "8", "item_codigo": "SIM-8-01", "cantidad": 2}],
            metodo_firma="TRAZO_TABLET",
            evidencia_firma="firma",
            usuario_deposito="1210",
            circuito=circuito,
            motivo="ENTREGA_ESTACIONAL",
        )


@pytest.mark.parametrize("motivo", ["", None, "OTRO"])
def test_rechaza_motivo_vacio_nulo_o_inventado(contenedor, motivo):
    with pytest.raises(MotivoReposicionInvalido):
        contenedor.registrar_entrega.ejecutar(
            numero_legajo="1077",
            items=[{"codigo": "69", "item_codigo": "SIM-69-01", "cantidad": 1}],
            metodo_firma="TRAZO_TABLET",
            evidencia_firma="firma",
            usuario_deposito="1210",
            circuito="ESPONTANEA",
            motivo=motivo,
        )


def test_campo_no_puede_ver_entregas_programadas(cliente):
    respuesta = cliente.get(
        "/entregas-programadas?temporada=VERANO&fecha=2026-11-02",
        headers={"X-Legajo-Usuario": "1501"},
    )
    assert respuesta.status_code == 403


def test_api_programada_muestra_fuente_y_estado_no_validado(cliente):
    respuesta = cliente.get(
        "/entregas-programadas?temporada=VERANO&fecha=2026-11-02&sector=CLA"
    )
    assert respuesta.status_code == 200
    assert respuesta.json()[0]["fuente_legajo"] == "SIMULADA"
    assert respuesta.json()[0]["estado_matriz"] == "PROPUESTA_SIN_VALIDAR"
