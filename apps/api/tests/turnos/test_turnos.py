from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from suite_juviar.modulos.turnos.api.app import crear_app
from suite_juviar.modulos.turnos.application.servicios import ConciliarTurnos
from suite_juviar.modulos.turnos.domain.entidades import (
    EstadoDia,
    EstadoImputacion,
    Fichada,
    FuenteSimuladaEnProduccion,
)
from suite_juviar.modulos.turnos.infrastructure.simulados import (
    ExportadorArchivoSimulado,
    FuenteFichadasSimulada,
)
from suite_juviar.plataforma.identidad.api.dependencias import PERMISOS_POR_PERFIL


def servicio(tmp_path, ahora=None):
    reloj = ahora or [datetime(2026, 8, 31, 12, tzinfo=UTC)]
    fuente = FuenteFichadasSimulada([
        Fichada("10", datetime(2026, 9, 1, 8, tzinfo=UTC), "ENTRADA"),
        Fichada("10", datetime(2026, 9, 1, 15, tzinfo=UTC), "SALIDA"),
    ])
    return ConciliarTurnos(fuente, ExportadorArchivoSimulado(tmp_path), lambda: reloj[0])


def test_cronograma_auditable_concilia_propone_y_no_imputa_solo(tmp_path):
    s = servicio(tmp_path)
    plan = s.cargar_cronograma("10", "Bodega", date(2026, 9, 1), time(8), time(16), "sup-1")
    dia = s.conciliar(date(2026, 9, 1), date(2026, 9, 1))[0]
    propuesta = s.imputaciones[str(dia.propuesta_id)]
    assert plan.autor == "sup-1" and plan.conocido_en.date() < plan.fecha
    assert dia.estado_dia is EstadoDia.SIN_INFORMAR
    assert propuesta.estado is EstadoImputacion.PROPUESTA


def test_lote_registra_actor_y_fecha_en_cada_dia_y_genera_bandeja_simulada(tmp_path):
    s = servicio(tmp_path)
    s.cargar_cronograma("10", "Bodega", date(2026, 9, 1), time(8), time(16), "sup-1")
    propuesta = s.conciliar(date(2026, 9, 1), date(2026, 9, 1))[0].propuesta_id
    salida = s.resolver_lote([str(propuesta)], "CAMBIAR", "rrhh-1", "Permiso especial")
    imputacion = s.imputaciones[str(propuesta)]
    assert imputacion.estado is EstadoImputacion.APROBADA
    assert imputacion.aprobada_por == "rrhh-1" and imputacion.resuelta_en is not None
    assert imputacion.motivo_final == "Permiso especial"
    assert salida.simulada is True and salida.estado == "GENERADO"
    contenido = Path(salida.archivo).read_text(encoding="utf-8")
    assert "DATOS SIMULADOS — SIN VALIDEZ" in contenido
    assert "NO ESCRIBE EN TIME" in contenido


def test_dia_cerrado_no_se_edita_y_cambio_tardio_se_versiona_y_reporta(tmp_path):
    reloj = [datetime(2026, 8, 31, 12, tzinfo=UTC)]
    s = servicio(tmp_path, reloj)
    original = s.cargar_cronograma("10", "Bodega", date(2026, 9, 1), time(8), time(16), "sup-1")
    reloj[0] = datetime(2026, 9, 10, 12, tzinfo=UTC)
    with pytest.raises(ValueError, match="día está cerrado"):
        s.cargar_cronograma("11", "Bodega", date(2026, 9, 1), time(8), time(16), "sup-1")
    vigente = s.registrar_cambio_tardio(str(original.id), time(7), time(15), "sup-1")
    assert vigente.reemplaza_id == original.id and vigente.cambio_tardio is True
    assert s.conciliar(date(2026, 9, 1), date(2026, 9, 1))[0].estado_dia is EstadoDia.REGULARIZADO_TARDE
    assert s.reporte_tardias(date(2026, 9, 1), date(2026, 9, 30))["por_sector"] == [
        {"sector": "Bodega", "dias_regularizados_tarde": 1}]


def test_pendiente_no_se_autoimputa_con_el_tiempo(tmp_path):
    reloj = [datetime(2026, 8, 31, 12, tzinfo=UTC)]
    s = servicio(tmp_path, reloj)
    s.cargar_cronograma("10", "Bodega", date(2026, 9, 1), time(8), time(16), "sup-1")
    identificador = str(s.conciliar(date(2026, 9, 1), date(2026, 9, 1))[0].propuesta_id)
    reloj[0] = datetime(2026, 9, 25, 12, tzinfo=UTC)
    assert s.imputaciones[identificador].estado is EstadoImputacion.PROPUESTA
    assert s.antiguedad_pendiente(s.imputaciones[identificador]) == 24


def test_supervisor_no_puede_operar_otro_sector_y_perfiles_sin_permiso_reciben_403(tmp_path):
    cliente = TestClient(crear_app(servicio(tmp_path)))
    entrada = {"legajo": "10", "sector": "Finca", "fecha": "2026-09-01", "desde": "08:00", "hasta": "16:00"}
    cabecera = {"X-Perfil-Simulado": "SUPERVISOR", "X-Sector-Simulado": "Bodega"}
    assert cliente.post("/cronogramas", json=entrada, headers=cabecera).status_code == 403
    assert cliente.get("/cronogramas", headers={"X-Perfil-Simulado": "DEPOSITO"}).status_code == 403


def test_control_negativo_permiso_de_aprobacion(tmp_path, monkeypatch):
    s = servicio(tmp_path)
    s.cargar_cronograma("10", "Bodega", date(2026, 9, 1), time(8), time(16), "sup-1")
    identificador = str(s.conciliar(date(2026, 9, 1), date(2026, 9, 1))[0].propuesta_id)
    cliente = TestClient(crear_app(s))
    cuerpo = {"ids": [identificador], "accion": "APROBAR"}
    cabecera = {"X-Perfil-Simulado": "SUPERVISOR"}
    assert cliente.post("/propuestas/resolver-lote", json=cuerpo, headers=cabecera).status_code == 403
    monkeypatch.setitem(PERMISOS_POR_PERFIL, "SUPERVISOR",
                        PERMISOS_POR_PERFIL["SUPERVISOR"] | {"turnos.imputacion.aprobar"})
    assert cliente.post("/propuestas/resolver-lote", json=cuerpo, headers=cabecera).status_code == 200


def test_api_semana_historial_filtros_y_rechazo_explicito(tmp_path):
    s = servicio(tmp_path)
    cliente = TestClient(crear_app(s))
    sup = {"X-Perfil-Simulado": "SUPERVISOR", "X-Sector-Simulado": "Bodega"}
    semana = {"sector": "Bodega", "asignaciones": [
        {"legajo": "10", "fecha": "2026-09-01", "desde": "08:00", "hasta": "16:00"}]}
    assert cliente.post("/cronogramas/semana", json=semana, headers=sup).status_code == 200
    conciliacion = cliente.get("/conciliacion", params={"desde": "2026-09-01", "hasta": "2026-09-01"},
                                headers={"X-Perfil-Simulado": "RRHH"})
    identificador = conciliacion.json()[0]["propuesta_id"]
    rechazo = cliente.post("/propuestas/resolver-lote", json={"ids": [identificador], "accion": "RECHAZAR"},
                           headers={"X-Perfil-Simulado": "RRHH", "X-Actor-Simulado": "rrhh-2"})
    assert rechazo.status_code == 200 and rechazo.json()["salida"] is None
    assert cliente.get("/bandeja", headers={"X-Perfil-Simulado": "RRHH"}).json() == []


def test_pantalla_marcada_y_produccion_rechaza_simulados(tmp_path):
    s = servicio(tmp_path)
    assert "DATOS SIMULADOS — SIN VALIDEZ" in TestClient(
        crear_app(s), headers={"X-Perfil-Simulado": "RRHH"}).get("/").text
    with pytest.raises(FuenteSimuladaEnProduccion):
        crear_app(s, "produccion")
