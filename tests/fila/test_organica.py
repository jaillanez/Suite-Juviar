"""Sesión de uva orgánica: quién pasa adelante, qué se bloquea y cómo se recibe."""

from modulos.fila.organica import (
    BLOQUEO_CONVENCIONAL,
    EstadoOrganica,
    bloqueo,
    certificados_con_prioridad,
    es_organico,
    recibida_como,
)

CERT = frozenset({"20-1"})
ABIERTA = EstadoOrganica(recibe=True, abierta=True)
CONVENCIONAL = EstadoOrganica(recibe=True)
PRIMEROS_DIAS = EstadoOrganica(recibe=True, prioridad=True)
SIN_ORGANICA = EstadoOrganica(recibe=False, abierta=True, prioridad=True)


def test_organico_es_declarado_y_certificado():
    assert es_organico(True, "20-1", CERT)
    assert not es_organico(True, "20-9", CERT)
    assert not es_organico(False, "20-1", CERT)


def test_la_organica_pasa_adelante_con_sesion_o_en_los_primeros_dias():
    assert certificados_con_prioridad(ABIERTA, CERT) == CERT
    assert certificados_con_prioridad(PRIMEROS_DIAS, CERT) == CERT
    assert certificados_con_prioridad(CONVENCIONAL, CERT) == frozenset()
    assert certificados_con_prioridad(SIN_ORGANICA, CERT) == frozenset()


def test_con_sesion_abierta_no_entra_convencional():
    assert bloqueo(ABIERTA, organico=False) == BLOQUEO_CONVENCIONAL
    assert bloqueo(ABIERTA, organico=True) is None
    assert bloqueo(CONVENCIONAL, organico=False) is None
    assert bloqueo(SIN_ORGANICA, organico=False) is None


def test_organica_fuera_de_sesion_se_recibe_como_convencional():
    assert recibida_como(ABIERTA, organico=True) == "organica"
    assert recibida_como(CONVENCIONAL, organico=True) == "convencional"
    assert recibida_como(PRIMEROS_DIAS, organico=True) == "convencional"
    assert recibida_como(ABIERTA, organico=False) == "convencional"


def test_estado_desde_la_base():
    assert EstadoOrganica.desde_fila(None) == EstadoOrganica()
    fila = {"recibe": True, "abierta": False, "prioridad": True, "origen": None}
    assert EstadoOrganica.desde_fila(fila) == PRIMEROS_DIAS
