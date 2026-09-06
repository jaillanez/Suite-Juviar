from datetime import UTC, datetime

import pytest

from suite_juviar.modulos.seleccion.application.extraccion import (
    CAMPOS_REQUERIDOS,
    ExtraerDatosCV,
)
from suite_juviar.modulos.seleccion.domain.modelos import (
    CampoExtraido,
    CVOriginal,
    OrigenCV,
)
from suite_juviar.modulos.seleccion.infrastructure.extraccion_pdf import (
    CamposPorReglasProvisorias,
    TextoPDF,
)
from suite_juviar.modulos.seleccion.infrastructure.extracciones_memoria import (
    ExtraccionesEnMemoria,
)
from suite_juviar.modulos.seleccion.infrastructure.memoria import OriginalesEnMemoria


def original(contenido: bytes = b"pdf") -> CVOriginal:
    ahora = datetime.now(UTC)
    return CVOriginal(
        id="cv-1",
        origen=OrigenCV.CORREO,
        referencia_fuente="correo:1",
        nombre_archivo="cv.pdf",
        contenido=contenido,
        sha256="hash",
        recibido_en=ahora,
        incorporado_en=ahora,
    )


class TextoFijo:
    def __init__(self, texto: str) -> None:
        self._texto = texto

    def extraer_texto(self, _contenido: bytes) -> str:
        return self._texto


def ejecutar(texto: str):
    originales = OriginalesEnMemoria()
    originales.guardar_original(original())
    extracciones = ExtraccionesEnMemoria()
    resultado = ExtraerDatosCV(
        originales,
        extracciones,
        TextoFijo(texto),
        CamposPorReglasProvisorias(),
    ).ejecutar("cv-1")
    return resultado, originales, extracciones


def test_extrae_todos_los_campos_con_fragmento_y_sin_verificarlos():
    extraccion, _, guardadas = ejecutar(
        """Edad: 32 años
Estudios: Secundario completo
Experiencia: 4 años en bodega
Oficio: Operario de mantenimiento
Localidad: Chimbas
Contacto: 264-555-0101"""
    )
    assert {campo.nombre for campo in extraccion.campos} == set(CAMPOS_REQUERIDOS)
    assert all(campo.fragmento_fuente for campo in extraccion.campos)
    assert all(campo.verificado is False for campo in extraccion.campos)
    assert extraccion.estado == "NO_VERIFICADO"
    assert extraccion.requiere_revision is False
    assert guardadas.obtener_extraccion("cv-1") == extraccion


def test_pdf_ilegible_va_a_revision_y_el_original_no_se_descarta():
    originales = OriginalesEnMemoria()
    guardado = original(b"esto no es un PDF")
    originales.guardar_original(guardado)
    extraccion = ExtraerDatosCV(
        originales,
        ExtraccionesEnMemoria(),
        TextoPDF(),
        CamposPorReglasProvisorias(),
    ).ejecutar("cv-1")
    assert extraccion.requiere_revision is True
    assert extraccion.campos_pendientes == CAMPOS_REQUERIDOS
    assert originales.obtener_original("cv-1") == guardado


@pytest.mark.parametrize(
    ("nombre", "valor", "fragmento"),
    [
        ("", "32", "Edad: 32"),
        (None, "32", "Edad: 32"),
        ("edad", "", "Edad: 32"),
        ("edad", None, "Edad: 32"),
        ("edad", "32", ""),
        ("edad", "32", None),
    ],
)
def test_rechaza_campo_extraido_vacio_o_nulo(nombre, valor, fragmento):
    with pytest.raises(ValueError):
        CampoExtraido(nombre=nombre, valor=valor, fragmento_fuente=fragmento)


def test_extraccion_automatica_no_puede_autoverificarse():
    with pytest.raises(ValueError, match="no puede marcar"):
        CampoExtraido(
            nombre="edad",
            valor="32",
            fragmento_fuente="Edad: 32",
            verificado=True,
        )
