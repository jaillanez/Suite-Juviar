"""CV que llegan por WhatsApp: entran a Selección como los del mail, con el teléfono de contacto."""

from datetime import UTC, datetime

from suite_juviar.modulos.seleccion.application.extraccion import ExtraerDatosCV
from suite_juviar.modulos.seleccion.application.ingesta import IngestarCVs
from suite_juviar.modulos.seleccion.application.whatsapp import IncorporarCVWhatsapp
from suite_juviar.modulos.seleccion.domain.modelos import OrigenCV
from suite_juviar.modulos.seleccion.infrastructure.extraccion_pdf import CamposPorReglasProvisorias
from suite_juviar.modulos.seleccion.infrastructure.extracciones_memoria import ExtraccionesEnMemoria
from suite_juviar.modulos.seleccion.infrastructure.memoria import OriginalesEnMemoria


class TextoFijo:
    def __init__(self, texto: str) -> None:
        self.texto = texto

    def extraer_texto(self, contenido: bytes) -> str:
        return self.texto


def _armar(texto: str):
    originales, extracciones = OriginalesEnMemoria(), ExtraccionesEnMemoria()
    servicio = IncorporarCVWhatsapp(
        IngestarCVs(originales),
        ExtraerDatosCV(originales, extracciones, TextoFijo(texto), CamposPorReglasProvisorias()),
        extracciones,
    )
    return servicio, originales, extracciones


def test_cv_por_whatsapp_entra_con_origen_y_telefono_de_contacto():
    servicio, originales, extracciones = _armar("Oficio: soldador\nLocalidad: Rawson")
    ahora = datetime(2026, 11, 20, tzinfo=UTC)
    assert servicio.ejecutar("5492645555555", "cv.pdf", b"%PDF-1.4 cv de prueba", ahora, "5492645555555:8:x")
    [original] = originales.listar_originales()
    assert original.origen is OrigenCV.WHATSAPP and original.fuente_simulada is False
    extraccion = extracciones.obtener_extraccion(original.id)
    contacto = next(c for c in extraccion.campos if c.nombre == "contacto")
    assert contacto.valor == "+5492645555555" and not contacto.verificado
    assert "contacto" not in extraccion.campos_pendientes and "oficio" not in extraccion.campos_pendientes


def test_el_mismo_cv_dos_veces_no_se_duplica():
    servicio, originales, _ = _armar("")
    ahora = datetime(2026, 11, 20, tzinfo=UTC)
    assert servicio.ejecutar("5492645555555", "cv.pdf", b"%PDF-1.4 mismo", ahora, "a:1")
    assert not servicio.ejecutar("5492645555555", "cv.pdf", b"%PDF-1.4 mismo", ahora, "a:2")
    assert len(originales.listar_originales()) == 1


def test_si_el_cv_ya_trae_contacto_no_se_pisa():
    servicio, originales, extracciones = _armar("Teléfono: 264 111 2222")
    servicio.ejecutar("5492645555555", "cv.pdf", b"%PDF-1.4 otro", datetime(2026, 11, 20, tzinfo=UTC), "b:1")
    [original] = originales.listar_originales()
    campos = [c for c in extracciones.obtener_extraccion(original.id).campos if c.nombre == "contacto"]
    assert [c.valor for c in campos] == ["264 111 2222"]
