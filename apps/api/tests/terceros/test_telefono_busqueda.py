import pytest

from suite_juviar.plataforma.terceros.busqueda import normalizar as norm_texto
from suite_juviar.plataforma.terceros.busqueda import terminos
from suite_juviar.plataforma.terceros.telefono import TelefonoInvalido, normalizar, para_mostrar

ESPERADO = "5492644567890"


@pytest.mark.parametrize("escrito", [
    "2644567890", "0264 4567890", "0264 15 456-7890", "264 15 4567890",
    "+54 9 264 4567890", "54 9 264 456 7890", "005492644567890",
    "5492644567890", "(0264) 15-4567890",
])
def test_formas_de_escribir_el_mismo_celular(escrito):
    assert normalizar(escrito) == ESPERADO


@pytest.mark.parametrize("malo", [None, "", "abc", "15", "26445678", "26445678901234"])
def test_rechaza_lo_que_no_es_celular(malo):
    with pytest.raises(TelefonoInvalido):
        normalizar(malo)


def test_para_mostrar():
    assert para_mostrar(ESPERADO) == "+54 9 264 4567890"


def test_texto_y_consulta():
    assert norm_texto("Rodríguez Néstor F.") == "RODRIGUEZ NESTOR F"
    assert terminos("r") == []
    assert terminos("nestor rodriguez") == ["NESTOR", "RODRIGUEZ"]
