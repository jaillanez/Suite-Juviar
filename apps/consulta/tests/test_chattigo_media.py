from consulta_publica.bot.chattigo_media import (
    cuerpo_documento,
    cuerpo_imagen,
)

URL = "https://bot.juviar.com.ar/archivos/abc.png"


def test_imagen_en_formato_meta():
    c = cuerpo_imagen("5492645123456", URL, "Cosecha 2026")
    assert c["type"] == "image" and c["messaging_product"] == "whatsapp"
    assert c["image"] == {"link": URL, "caption": "Cosecha 2026"}


def test_imagen_sin_epigrafe_no_manda_caption_vacio():
    assert "caption" not in cuerpo_imagen("549", URL)["image"]


def test_documento_lleva_nombre_de_archivo():
    c = cuerpo_documento("549", URL, "cosecha_G03436.pdf")
    assert c["document"]["filename"] == "cosecha_G03436.pdf"


def test_epigrafe_largo_se_recorta():
    assert len(cuerpo_imagen("549", URL, "x" * 2000)["image"]["caption"]) == 1024
