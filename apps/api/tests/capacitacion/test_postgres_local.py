from datetime import date
from uuid import uuid4

import pytest

from suite_juviar.modulos.capacitacion.domain.modelos import Asistencia, Dictado, Participante, Tema
from suite_juviar.modulos.capacitacion.infrastructure.postgres import (
    CapacitacionPostgreSQL,
    asistencia_visible,
)
from suite_juviar.plataforma.cripto.adaptador import ProtectorAESGCM


@pytest.mark.local
def test_capacitacion_postgresql_cifra_identidad_y_recupera_asistencia():
    dsn = "postgresql:///juviar_suite_local"
    repositorio = CapacitacionPostgreSQL(dsn, ProtectorAESGCM(b"h" * 32, b"c" * 32))
    sufijo = uuid4().hex
    tema = Tema(f"T-{sufijo}", "Tema local de prueba", 1.5)
    dictado = Dictado(f"D-{sufijo}", tema.id, date(2026, 9, 6), "Instructor de prueba")
    asistencia = Asistencia(
        dictado.id,
        Participante("1901", "Persona de Prueba", supervisor=True),
        True,
        None,
        "PENDIENTE_FIRMA_PAPEL",
    )
    repositorio.guardar_tema(tema)
    repositorio.guardar_dictado(dictado)
    repositorio.guardar_asistencia(asistencia)
    assert repositorio.obtener_tema(tema.id) == tema
    assert repositorio.obtener_dictado(dictado.id) == dictado
    recuperada = repositorio.asistencias_del_dictado(dictado.id)
    assert recuperada == [asistencia]

    visibles = asistencia_visible(dsn, dictado.id)
    assert len(visibles) == 1
    assert "1901" not in repr(visibles)
    assert "Persona de Prueba" not in repr(visibles)
