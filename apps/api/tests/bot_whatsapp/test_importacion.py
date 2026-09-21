from pathlib import Path

import pytest

from suite_juviar.plataforma.terceros.infrastructure.importar_whatsapp import normalizar


@pytest.mark.parametrize(
    ("entrada", "salida"),
    [("+54 9 264 555-1212", "5492645551212"), ("5492645551212", "5492645551212"), ("", "")],
)
def test_normalizar_telefono(entrada, salida):
    assert normalizar(entrada) == salida


def test_migraciones_y_servicio_no_contienen_secretos():
    raiz = Path(__file__).parents[4]
    ejemplo = (raiz / "infra/bot.env.example").read_text()
    servicio = (raiz / "infra/systemd/bot-whatsapp.service").read_text()
    assert "CHATTIGO_CLAVE=\n" in ejemplo
    assert "EnvironmentFile=/etc/suite/bot.env" in servicio
    assert "enable --now" not in servicio
