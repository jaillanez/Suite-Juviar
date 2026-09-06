from datetime import date
from io import BytesIO

from pypdf import PdfReader


def _entregar(contenedor, identificador: str, codigo: str, item: str, fecha: date):
    return contenedor.registrar_entrega.ejecutar(
        numero_legajo="1077",
        items=[{"codigo": codigo, "item_codigo": item, "cantidad": 1}],
        metodo_firma="TRAZO_TABLET",
        evidencia_firma="data:image/png;base64,AAAA",
        usuario_deposito="1210",
        fecha=fecha,
        id_entrega=identificador,
        circuito="ESPONTANEA",
        motivo="ROTURA",
    )


def _texto(pdf: bytes) -> str:
    return "\n".join(pagina.extract_text() or "" for pagina in PdfReader(BytesIO(pdf)).pages)


def test_reposicion_agrega_renglon_en_nueva_version_y_conserva_el_original(contenedor):
    primera = _entregar(
        contenedor,
        "CONSTANCIA-V1",
        "69",
        "SIM-69-02",
        date(2026, 3, 12),
    )
    original_v1 = contenedor.obtener_constancia_pdf.ejecutar(primera.id)
    assert original_v1 is not None
    bytes_v1 = original_v1.contenido
    hash_v1 = original_v1.sha256
    assert original_v1.version == 1
    assert original_v1.anula_a is None
    assert original_v1.entregas_incluidas == ("CONSTANCIA-V1",)

    reposicion = _entregar(
        contenedor,
        "CONSTANCIA-V2",
        "68",
        "SIM-68-01",
        date(2026, 3, 20),
    )
    original_v2 = contenedor.obtener_constancia_pdf.ejecutar(reposicion.id)
    assert original_v2 is not None
    assert original_v2.version == 2
    assert original_v2.anula_a == "CONSTANCIA-V1"
    assert original_v2.entregas_incluidas == ("CONSTANCIA-V1", "CONSTANCIA-V2")
    texto_v2 = _texto(original_v2.contenido)
    assert "SIM-69-02" in texto_v2
    assert "SIM-68-01" in texto_v2
    assert "12/03/2026" in texto_v2
    assert "20/03/2026" in texto_v2

    recuperado_v1 = contenedor.obtener_constancia_pdf.ejecutar(primera.id)
    assert recuperado_v1 is not None
    assert recuperado_v1.contenido == bytes_v1
    assert recuperado_v1.sha256 == hash_v1
    assert "SIM-68-01" not in _texto(recuperado_v1.contenido)


def test_api_conserva_constancia_al_confirmar_la_entrega(cliente):
    respuesta = cliente.post(
        "/entregas",
        json={
            "id_cliente": "TABLET-CONSTANCIA-1",
            "legajo": "1077",
            "items": [{"codigo": "69", "item_codigo": "SIM-69-02", "cantidad": 1}],
            "evidencia_firma": "data:image/png;base64,AAAA",
            "circuito": "ESPONTANEA",
            "motivo": "DESGASTE",
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["version_constancia"] == 1
    assert respuesta.json()["anula_a"] is None
    assert cliente.get("/constancias/TABLET-CONSTANCIA-1.pdf").status_code == 200
