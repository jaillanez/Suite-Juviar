from fila_app.web import guardia


def _script():
    html = guardia("chimbas")
    return html, html.split("<script>", 1)[1].split("</script>", 1)[0]


def test_no_usa_las_cajas_del_navegador():
    """prompt, confirm y alert confunden al guardia: todo se pregunta con botones en pantalla."""
    _, script = _script()
    for caja in ("prompt(", "confirm(", "alert("):
        assert caja not in script


def test_los_motivos_se_eligen_con_botones_y_palabras_simples():
    html, script = _script()
    assert 'id="velo"' in html
    assert "No responde" in script and "La patente no coincide" in script
    assert "¿La carga es orgánica?" in script
