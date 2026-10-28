from datetime import date, datetime, timedelta, timezone

import pytest
from consulta_publica.bot.archivos import (
    MINUTOS_VIGENCIA,
    ArchivoInvalido,
    nombre_reporte,
    preparar,
)

AHORA = datetime(2026, 3, 17, 10, 0, tzinfo=timezone.utc)


def test_el_enlace_lleva_token_largo_y_extension():
    a = preparar(b"imagen", "png", "estadisticas.png", AHORA)
    url = a.url("https://bot.juviar.com.ar")
    assert url.endswith(".png") and len(a.token) >= 40
    assert url.startswith("https://bot.juviar.com.ar/archivos/")


def test_vence_a_la_media_hora():
    a = preparar(b"x", "pdf", "r.pdf", AHORA)
    assert a.vigente(AHORA + timedelta(minutes=MINUTOS_VIGENCIA - 1))
    assert not a.vigente(AHORA + timedelta(minutes=MINUTOS_VIGENCIA, seconds=1))


def test_dos_archivos_no_comparten_token():
    assert preparar(b"x", "png", "a", AHORA).token != preparar(b"x", "png", "a", AHORA).token


@pytest.mark.parametrize("extension", ["exe", "html", "svg", ""])
def test_solo_png_y_pdf(extension):
    with pytest.raises(ArchivoInvalido):
        preparar(b"x", extension, "a", AHORA)


def test_vacio_o_enorme_se_rechaza():
    with pytest.raises(ArchivoInvalido):
        preparar(b"", "png", "a", AHORA)
    with pytest.raises(ArchivoInvalido):
        preparar(b"x" * (6 * 1024 * 1024), "png", "a", AHORA)


def test_nombre_del_reporte():
    assert nombre_reporte("G03436", date(2025, 12, 1), date(2026, 3, 17)) == \
        "cosecha_G03436_20251201_20260317.pdf"
