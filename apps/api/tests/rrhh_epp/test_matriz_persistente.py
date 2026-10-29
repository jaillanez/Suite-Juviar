from suite_juviar.modulos.rrhh_epp.domain.modelos_mvp import RequisitoEPP
from suite_juviar.modulos.rrhh_epp.infrastructure.catalogo_yaml import CatalogoYAML
from suite_juviar.modulos.rrhh_epp.mvp import RAIZ


def catalogo(ruta):
    d = RAIZ / "data"
    return CatalogoYAML(d / "catalogo_rd068.yaml", d / "matriz_sector_puesto_epp.yaml",
                        d / "vida_util_referencial.yaml", d / "catalogo_items.yaml", ruta)


def test_los_cambios_de_la_matriz_sobreviven_a_un_reinicio(tmp_path):
    ruta = tmp_path / "matriz_cambios.json"
    primero = catalogo(ruta)
    codigo = next(iter(primero._elementos))
    requisito = RequisitoEPP(codigo, 2, "ANUAL", "TODO_EL_ANIO", True, "riesgo de prueba", "PUESTO")
    primero.guardar_matriz_puesto("OP-BOD", [requisito], "rrhh@enav.com")
    segundo = catalogo(ruta)
    assert segundo.matriz_puesto("OP-BOD") == [requisito]
    assert segundo.historial_matriz[-1]["autor"] == "rrhh@enav.com"
    assert catalogo(None).matriz_puesto("OP-BOD") != [requisito]


def test_la_firma_de_hys_no_vale_si_la_matriz_cambio_despues(tmp_path):
    ruta = tmp_path / "matriz_cambios.json"
    c = catalogo(ruta)
    codigo = next(iter(c._elementos))
    c.guardar_matriz_puesto("OP-BOD", [RequisitoEPP(codigo, 1, "ANUAL", "TODO_EL_ANIO", True, "x", "PUESTO")], "rrhh")
    c.validar_matriz("hys@enav.com")
    assert catalogo(ruta).estado_matriz == "VALIDADA_HYS"
    import json
    datos = json.loads(ruta.read_text())
    datos["puestos"]["OP-BOD"][0]["cantidad"] = 9
    datos["puestos"]["OP-BOD"].append({"codigo": "NO-EXISTE", "cantidad": 1, "frecuencia": "ANUAL",
                                       "temporada": "TODO_EL_ANIO", "obligatorio": True})
    ruta.write_text(json.dumps(datos))
    alterado = catalogo(ruta)
    assert alterado.estado_matriz == "PROPUESTA_SIN_VALIDAR"
    assert [r.codigo for r in alterado.matriz_puesto("OP-BOD")] == [codigo]


def test_un_archivo_danado_no_impide_arrancar(tmp_path):
    ruta = tmp_path / "matriz_cambios.json"
    ruta.write_text("{roto")
    assert catalogo(ruta).matriz_puesto("OP-BOD") is not None
    assert (tmp_path / "matriz_cambios.danado").exists()
