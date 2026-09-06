import pytest

from suite_juviar.plataforma.terceros.domain.entidades import (
    DUENO_POSTULANTES,
    Tercero,
    TipoTercero,
)


def postulante(**cambios) -> Tercero:
    datos = {
        "cuit": None,
        "razon_social": "Ana Pérez",
        "tipo": TipoTercero.POSTULANTE,
        "dni": "30111222",
        "email": "ana@example.test",
    }
    datos.update(cambios)
    return Tercero(**datos)


def test_postulante_es_un_tercero_con_dueno_rrhh():
    persona = postulante()
    assert persona.tipo is TipoTercero.POSTULANTE
    assert persona.clave_registro == ("AR-DNI", "30111222")
    assert DUENO_POSTULANTES == "RRHH"


def test_correo_es_clave_provisoria_cuando_no_hay_dni():
    persona = postulante(dni=None, email="Ana.Perez@example.test")
    assert persona.clave_registro == ("EMAIL", "ana.perez@example.test")


@pytest.mark.parametrize(
    ("dni", "email"),
    [(None, None), ("", None), (None, ""), ("   ", "   ")],
)
def test_rechaza_postulante_sin_dni_y_sin_correo(dni, email):
    with pytest.raises(ValueError, match="DNI o correo"):
        postulante(dni=dni, email=email)


@pytest.mark.parametrize("dni", ["30.111.222", "ABC", "123X"])
def test_rechaza_dni_no_numerico(dni):
    with pytest.raises(ValueError, match="dígitos"):
        postulante(dni=dni)


def test_al_ingresar_se_vincula_sin_convertir_ni_borrar_el_postulante():
    persona = postulante()
    persona.vincular_alta_en_nexus("1842")
    assert persona.tipo is TipoTercero.POSTULANTE
    assert persona.activo is True
    assert persona.legajo_vinculado == "1842"


@pytest.mark.parametrize("legajo", ["", "   ", None])
def test_rechaza_vinculo_a_legajo_vacio_o_nulo(legajo):
    with pytest.raises(ValueError, match="no puede estar vacío"):
        postulante().vincular_alta_en_nexus(legajo)
