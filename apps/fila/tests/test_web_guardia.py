from fila_app.web import guardia


def test_selector_de_motivos_conserva_escapes_javascript():
    html = guardia("chimbas")
    script = html.split("<script>", 1)[1].split("</script>", 1)[0]

    assert r".join('\n')" in script
    assert r"titulo+'\n'+lista" in script
