from datetime import UTC, datetime

import pytest

from suite_juviar.modulos.seleccion.application.ingesta import IngestarCVs
from suite_juviar.modulos.seleccion.domain.modelos import DocumentoEntrante, OrigenCV
from suite_juviar.modulos.seleccion.infrastructure.fuentes_archivo import (
    BandejaCorreoLocalSimulada,
    CarpetaServidorCV,
)
from suite_juviar.modulos.seleccion.infrastructure.memoria import OriginalesEnMemoria


def test_carpeta_conserva_el_pdf_original_sin_moverlo(tmp_path):
    contenido = b"%PDF-1.7 CV original"
    archivo = tmp_path / "postulante.pdf"
    archivo.write_bytes(contenido)
    (tmp_path / "notas.txt").write_text("no es un CV PDF", encoding="utf-8")
    repositorio = OriginalesEnMemoria()

    incorporados = IngestarCVs(repositorio).ejecutar(CarpetaServidorCV(tmp_path))

    assert len(incorporados) == 1
    assert incorporados[0].contenido == contenido
    assert incorporados[0].dueno_dato == "RRHH"
    assert incorporados[0].fuente_simulada is False
    assert archivo.read_bytes() == contenido
    assert (tmp_path / "notas.txt").exists()


def test_ingesta_repetida_no_duplica_el_original(tmp_path):
    (tmp_path / "cv.pdf").write_bytes(b"%PDF CV")
    fuente = CarpetaServidorCV(tmp_path)
    repositorio = OriginalesEnMemoria()
    caso = IngestarCVs(repositorio)
    assert len(caso.ejecutar(fuente)) == 1
    assert caso.ejecutar(fuente) == []


def test_correo_local_se_declara_simulado(tmp_path):
    (tmp_path / "adjunto.pdf").write_bytes(b"%PDF adjunto")
    fuente = BandejaCorreoLocalSimulada(tmp_path)
    original = IngestarCVs(OriginalesEnMemoria()).ejecutar(fuente)[0]
    assert fuente.estado == "SIMULADO_SIN_CREDENCIALES_DE_CORREO"
    assert original.origen is OrigenCV.CORREO
    assert original.fuente_simulada is True


@pytest.mark.parametrize(
    ("referencia", "nombre", "contenido"),
    [
        ("", "cv.pdf", b"x"),
        (None, "cv.pdf", b"x"),
        ("archivo:1", "", b"x"),
        ("archivo:1", None, b"x"),
        ("archivo:1", "cv.pdf", b""),
        ("archivo:1", "cv.pdf", None),
    ],
)
def test_rechaza_original_con_campos_vacios_o_nulos(referencia, nombre, contenido):
    with pytest.raises(ValueError):
        DocumentoEntrante(
            origen=OrigenCV.CARPETA_CHIMBAS,
            referencia_fuente=referencia,
            nombre_archivo=nombre,
            contenido=contenido,
            recibido_en=datetime.now(UTC),
            fuente_simulada=False,
        )
