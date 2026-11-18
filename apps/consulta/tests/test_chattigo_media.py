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


def test_mensaje_con_foto_trae_el_identificador_y_el_epigrafe():
    from consulta_publica.bot.meta import extraer_mensajes

    payload = {"entry": [{"changes": [{"value": {"messages": [
        {"id": "w1", "from": "5492640000000", "type": "image", "image": {"id": "MEDIA.123", "caption": "BOM-0003"}},
        {"id": "w2", "from": "5492640000000", "type": "image", "image": {"id": "../malo"}},
    ]}}]}]}
    primero, segundo = extraer_mensajes(payload)
    assert (primero.tipo, primero.texto, primero.media_id) == ("image", "BOM-0003", "MEDIA.123")
    assert segundo.media_id is None and segundo.texto is None
