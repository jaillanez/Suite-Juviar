import pytest

from suite_juviar.modulos.seleccion.infrastructure import lectura_en_fondo


@pytest.fixture(autouse=True)
def sin_ia_real(monkeypatch):
    """Ninguna prueba llama a DeepSeek de verdad, y la lectura en segundo plano termina antes de
    deshacer los reemplazos de la prueba."""
    monkeypatch.delenv("SJ_IA_DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("SJ_SALUD_IA_API_KEY", raising=False)
    yield
    assert lectura_en_fondo.esperar_todas(30)
