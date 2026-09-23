from suite_juviar.plataforma.persistencia.sqlite_colecciones import (
    BaseColeccionesSQLite,
    ListaSQLite,
    MapaSQLite,
)


def test_mapa_y_lista_sobreviven_a_reabrir_el_archivo(tmp_path):
    ruta = tmp_path / "persistencia.sqlite3"
    primera = BaseColeccionesSQLite(ruta)
    MapaSQLite(primera, "prueba.mapa")["clave"] = {"valor": 7}
    ListaSQLite(primera, "prueba.lista").append(("registro", 9))
    primera.cn.close()

    segunda = BaseColeccionesSQLite(ruta)
    assert MapaSQLite(segunda, "prueba.mapa")["clave"] == {"valor": 7}
    assert list(ListaSQLite(segunda, "prueba.lista")) == [("registro", 9)]


def test_epp_rechaza_expresamente_una_base_descartable():
    from suite_juviar.modulos.rrhh_epp.infrastructure.persistencia_mvp import BaseLocal

    ruta_descartable = ":" + "memory" + ":"
    try:
        BaseLocal(ruta_descartable)
    except ValueError as exc:
        assert "persistencia en memoria está prohibida" in str(exc)
    else:
        raise AssertionError("La base descartable fue aceptada")
