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


def test_los_motivos_se_esperan_antes_de_enviar():
    _, script = _script()
    assert "motivo=await elegirMotivo(motivosSalto" in script
    assert "const motivo=await elegirMotivo(motivosCierre" in script


def test_sesion_organica_y_foto_de_patente():
    html, script = _script()
    assert 'id="organica"' in html and 'capture="environment"' in html
    assert "Abrir sesión orgánica" in script and "Cerrar sesión orgánica" in script
    assert "se recibe como convencional" in script
    assert "Foto patente" in script and "/foto'" in script
