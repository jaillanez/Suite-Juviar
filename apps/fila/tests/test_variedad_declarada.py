from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from fila_app.modelos import AltaGuardia, AltaPublica, Confirmacion
from fila_app.web import guardia, porton

MOMENTO = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)


def _alta(**extra):
    return AltaPublica(
        sede="chimbas", patente="AB123CD", productor="Pérez", id_cliente=uuid4(), **extra
    )


def _script(html: str) -> str:
    return html.split("<script>", 1)[1].split("</script>", 1)[0]


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("  Malbec  ", "Malbec"),
        ("Cabernet   Sauvignon", "Cabernet Sauvignon"),
        ("", None),
        ("   ", None),
        (None, None),
        ("x" * 80, "x" * 60),
    ],
)
def test_alta_publica_normaliza_variedad(entrada, esperado):
    assert _alta(variedad=entrada).variedad == esperado


def test_alta_publica_sin_variedad_sigue_valiendo():
    alta = _alta()
    assert alta.variedad is None
    assert alta.model_dump()["variedad"] is None


def test_variedad_no_texto_se_rechaza():
    with pytest.raises(ValidationError):
        _alta(variedad=123)


def test_confirmacion_distingue_variedad_omitida_de_borrada():
    base = {"id_cliente": uuid4(), "clientecuit": "20123456789", "momento_cliente": MOMENTO}
    omitida = Confirmacion(**base)
    borrada = Confirmacion(**base, variedad="  ")
    assert "variedad" not in omitida.model_fields_set
    assert "variedad" in borrada.model_fields_set and borrada.variedad is None


def test_alta_guardia_acepta_variedad():
    alta = AltaGuardia(
        id_cliente=uuid4(),
        clientecuit="20123456789",
        momento_cliente=MOMENTO,
        sede="lavalle",
        patente="AB123CD",
        productor="Pérez",
        variedad=" Bonarda ",
    )
    assert alta.model_dump()["variedad"] == "Bonarda"


def test_porton_incluye_campo_variedad_con_sugerencias_escapadas():
    html = porton("chimbas", ["Malbec", 'Rara"<b>'])
    assert 'for="variedad"' in html and "Variedad de uva que trae" in html
    assert 'id="variedad" list="variedades" maxlength="60"' in html
    assert '<datalist id="variedades"><option value="Malbec">' in html
    assert 'value="Rara&quot;&lt;b&gt;"' in html and 'Rara"<b>' not in html
    assert "variedad:$('#variedad').value.trim()||null" in _script(html)


def test_porton_sin_sugerencias_queda_texto_libre():
    html = porton("chimbas")
    assert 'id="variedad"' in html
    assert '<datalist id="variedades"></datalist>' in html


def test_guardia_muestra_y_edita_variedad():
    html = guardia("chimbas", ["Malbec"])
    script = _script(html)
    assert 'id="variedadGuardia"' in html and "Variedad de uva declarada" in html
    assert '<datalist id="variedadesGuardia"><option value="Malbec">' in html
    assert "elegirProductor(x?.variedad_declarada)" in script
    assert script.count("variedad:p.variedad") == 2
    assert 'class="tag uva"' in script and "esc(x.variedad_declarada)" in script
    assert "variedadGuardia.value=variedadPrevia||''" in script
