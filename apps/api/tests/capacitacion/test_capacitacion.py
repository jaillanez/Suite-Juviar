from datetime import date
from pathlib import Path

import pytest

from suite_juviar.modulos.capacitacion.application.servicios import (
    AnularAsistencia,
    RegistrarAsistencia,
    ReportesCapacitacion,
    planilla_imprimible,
)
from suite_juviar.modulos.capacitacion.domain.modelos import Dictado, Participante, Tema
from suite_juviar.modulos.capacitacion.infrastructure.configuracion_yaml import (
    ConfiguracionCapacitacionYAML,
)
from suite_juviar.modulos.capacitacion.infrastructure.memoria import CapacitacionEnMemoria
from suite_juviar.plataforma.firma.domain.entidades import MetodoFirmaElectronica
from suite_juviar.plataforma.firma.infrastructure.simulada import MotorFirmaSimulado

CONFIGURACION = (
    Path(__file__).resolve().parents[2]
    / "src/suite_juviar/modulos/capacitacion/data/configuracion.yaml"
)


def configuracion() -> ConfiguracionCapacitacionYAML:
    return ConfiguracionCapacitacionYAML(CONFIGURACION)


def repositorio() -> CapacitacionEnMemoria:
    repo = CapacitacionEnMemoria()
    repo.guardar_tema(Tema("SEG", "Seguridad en bodega", 2))
    repo.guardar_dictado(Dictado("SEG-1", "SEG", date(2026, 3, 1), "HyS"))
    repo.guardar_dictado(Dictado("SEG-2", "SEG", date(2026, 3, 8), "HyS"))
    repo.guardar_dictado(Dictado("SEG-3", "SEG", date(2026, 3, 15), "HyS"))
    return repo


@pytest.mark.asyncio
async def test_asistencia_electronica_usa_el_motor_compartido_y_se_declara_simulada():
    repo = repositorio()
    asistencia = await RegistrarAsistencia(repo, MotorFirmaSimulado()).ejecutar(
        "SEG-1",
        Participante("1001", "Ana Pérez"),
        True,
        MetodoFirmaElectronica.TRAZO_TABLET,
        b"trazo",
    )
    assert asistencia.firma_id is not None
    assert asistencia.estado_firma == "SIMULADO_SIN_VALIDEZ_LEGAL"


@pytest.mark.asyncio
async def test_planilla_en_papel_deja_firma_pendiente():
    repo = repositorio()
    asistencia = await RegistrarAsistencia(repo, MotorFirmaSimulado()).ejecutar(
        "SEG-1", Participante("1001", "Ana Pérez"), True
    )
    assert asistencia.estado_firma == "PENDIENTE_FIRMA_PAPEL"
    assert asistencia.firma_id is None
    texto = planilla_imprimible("Seguridad en bodega", date(2026, 3, 1))
    assert "SIN VALIDEZ LEGAL" in texto
    assert "Firma" in texto


@pytest.mark.asyncio
async def test_rechaza_firma_sin_evidencia_vacia_o_nula():
    repo = repositorio()
    caso = RegistrarAsistencia(repo, MotorFirmaSimulado())
    for evidencia in (b"", None):
        with pytest.raises(ValueError, match="requiere evidencia"):
            await caso.ejecutar(
                "SEG-1",
                Participante("1001", "Ana Pérez"),
                True,
                MetodoFirmaElectronica.TRAZO_TABLET,
                evidencia,
            )


@pytest.mark.asyncio
async def test_reportes_suman_dictados_por_tema_persona_y_anio():
    repo = repositorio()
    caso = RegistrarAsistencia(repo, MotorFirmaSimulado())
    persona = Participante("1001", "Ana Pérez")
    await caso.ejecutar("SEG-1", persona, True)
    await caso.ejecutar("SEG-2", persona, True)
    await caso.ejecutar("SEG-3", persona, False)
    reportes = ReportesCapacitacion(repo, configuracion())
    assert reportes.porcentaje_tema("SEG") == 66.67
    assert reportes.porcentaje_persona("1001") == 66.67
    assert reportes.horas_por_persona("1001", 2026) == 4


@pytest.mark.asyncio
async def test_alerta_solo_supervisores_con_asistencia_baja():
    repo = repositorio()
    caso = RegistrarAsistencia(repo, MotorFirmaSimulado())
    supervisor = Participante("2001", "Supervisor Uno", supervisor=True)
    operario = Participante("2002", "Operario Dos", supervisor=False)
    for persona in (supervisor, operario):
        await caso.ejecutar("SEG-1", persona, True)
        await caso.ejecutar("SEG-2", persona, False)
    alertas = ReportesCapacitacion(repo, configuracion()).alertas_supervisores()
    assert [(alerta.legajo, alerta.porcentaje) for alerta in alertas] == [("2001", 50.0)]


@pytest.mark.parametrize("valor", ["", None])
def test_rechaza_tema_con_nombre_vacio_o_nulo(valor):
    with pytest.raises(ValueError, match="no puede estar vacío"):
        Tema("SEG", valor, 2)


@pytest.mark.parametrize("horas", [0, -1, None, True])
def test_rechaza_horas_vacias_o_invalidas(horas):
    with pytest.raises(ValueError, match="mayores a cero"):
        Tema("SEG", "Seguridad", horas)


def test_configuracion_declara_dueno_y_estado():
    datos = configuracion()
    assert datos.dueno_dato == "RRHH"
    assert datos.estado == "PROPUESTA_SIN_VALIDAR"
    assert datos.umbral_supervisor == 80


@pytest.mark.asyncio
async def test_asistencia_mal_cargada_se_anula_sin_borrar_el_original():
    repo = repositorio()
    persona = Participante("1001", "Ana Pérez")
    await RegistrarAsistencia(repo, MotorFirmaSimulado()).ejecutar("SEG-1", persona, True)
    anulacion = AnularAsistencia(repo).ejecutar(
        "SEG-1",
        "1001",
        "Se marcó presente por error",
        "rrhh-01",
    )
    assert anulacion.motivo == "Se marcó presente por error"
    assert repo.obtener_anulacion("SEG-1", "1001") == anulacion
    assert ("SEG-1", "1001") in repo.asistencias
    assert repo.asistencias_del_dictado("SEG-1") == []


@pytest.mark.parametrize("motivo", ["", None])
def test_rechaza_anulacion_con_motivo_vacio_o_nulo(motivo):
    from datetime import UTC, datetime

    from suite_juviar.modulos.capacitacion.domain.modelos import AnulacionAsistencia

    with pytest.raises(ValueError, match="motivo"):
        AnulacionAsistencia("SEG-1", "1001", motivo, "rrhh-01", datetime.now(UTC))
