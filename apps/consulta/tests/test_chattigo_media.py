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


def _cliente(manejador):
    import httpx
    from consulta_publica.bot.chattigo import ClienteChattigo, ConfigChattigo

    config = ConfigChattigo(base_url="https://api.chattigo.com", usuario="u", clave="c", did="549264", version="v15.0",
                            prefijo_auth="")
    return ClienteChattigo(config, httpx.Client(transport=httpx.MockTransport(manejador)))


def test_la_foto_solo_se_baja_de_whatsapp_y_con_tope():
    import httpx
    import pytest
    from consulta_publica.bot.chattigo import ErrorChattigo

    def manejador(pedido):
        if pedido.url.path == "/login":
            return httpx.Response(200, json={"access_token": "t"})
        if pedido.url.path == "/v15.0/MEDIA.1":
            return httpx.Response(200, json={"url": "https://lookaside.fbsbx.com/x", "mime_type": "image/jpeg"})
        if pedido.url.path == "/v15.0/MEDIA.2":
            return httpx.Response(200, json={"url": "https://169.254.169.254/latest", "mime_type": "image/jpeg"})
        if pedido.url.path == "/v15.0/MEDIA.3":
            return httpx.Response(200, json={"url": "https://lookaside.fbsbx.com/grande", "mime_type": "image/jpeg"})
        if pedido.url.path == "/grande":
            return httpx.Response(200, content=b"0" * 3_000_001)
        return httpx.Response(200, content=b"\xff\xd8" + b"0" * 2000)

    cliente = _cliente(manejador)
    contenido, tipo = cliente.descargar_media("MEDIA.1")
    assert tipo == "image/jpeg" and len(contenido) == 2002
    with pytest.raises(ErrorChattigo, match="dirección"):
        cliente.descargar_media("MEDIA.2")
    with pytest.raises(ErrorChattigo, match="grande"):
        cliente.descargar_media("MEDIA.3")
