from datetime import UTC, datetime
from pathlib import Path

import pytest

from suite_juviar.modulos.seleccion.application.ranking import (
    AvisarNuevaCoincidencia,
    EvaluarBusqueda,
    ordenar_resultados,
)
from suite_juviar.modulos.seleccion.domain.modelos import (
    Busqueda,
    CampoExtraido,
    ExtraccionCV,
    PerfilBusqueda,
)
from suite_juviar.modulos.seleccion.infrastructure.notificador_memoria import (
    NotificadorEnMemoria,
)
from suite_juviar.modulos.seleccion.infrastructure.perfiles_yaml import CriteriosPerfilYAML

RUTA = (
    Path(__file__).resolve().parents[2]
    / "src/suite_juviar/modulos/seleccion/data/criterios_perfil.yaml"
)


def busqueda(**cambios) -> Busqueda:
    datos = {
        "id": "TEMP-2026",
        "nombre": "Temporarios de bodega",
        "perfil": PerfilBusqueda.BODEGA,
        "definido_por": "rrhh-01",
        "definido_en": datetime.now(UTC),
        "edad_minima": 18,
        "edad_maxima": 45,
        "secundaria_completa": True,
    }
    datos.update(cambios)
    return Busqueda(**datos)


def extraccion(id_original: str = "cv-1", *, completa: bool = True) -> ExtraccionCV:
    valores = {
        "edad_o_fecha_nacimiento": "32 años",
        "nivel_estudios": "Secundario completo",
        "experiencia": "Cuatro temporadas como operario de bodega",
        "oficio": "Operario",
        "localidad": "Chimbas",
        "contacto": "2645550101",
    }
    if not completa:
        valores.pop("edad_o_fecha_nacimiento")
    campos = tuple(
        CampoExtraido(nombre=nombre, valor=valor, fragmento_fuente=f"{nombre}: {valor}")
        for nombre, valor in valores.items()
    )
    return ExtraccionCV(
        id_original=id_original,
        campos=campos,
        campos_pendientes=() if completa else ("edad_o_fecha_nacimiento",),
        extraido_en=datetime.now(UTC),
    )


def evaluador() -> EvaluarBusqueda:
    return EvaluarBusqueda(CriteriosPerfilYAML(RUTA))


def test_resultado_dice_por_que_quedo_dentro():
    resultado = evaluador().ejecutar(busqueda(), extraccion())
    assert resultado.cumple is True
    assert resultado.requiere_revision is False
    assert len(resultado.razones) == 3
    assert all(razon.startswith("DENTRO:") for razon in resultado.razones)


def test_resultado_dice_por_que_quedo_fuera():
    resultado = evaluador().ejecutar(busqueda(edad_maxima=25), extraccion())
    assert resultado.cumple is False
    assert any("edad 32 mayor" in razon for razon in resultado.razones)


def test_dato_ilegible_va_a_revision_y_no_al_fondo_del_ranking():
    dentro = evaluador().ejecutar(busqueda(), extraccion("dentro"))
    revisar = evaluador().ejecutar(busqueda(), extraccion("revisar", completa=False))
    fuera = evaluador().ejecutar(busqueda(edad_maxima=25), extraccion("fuera"))
    ordenados = ordenar_resultados([fuera, revisar, dentro])
    assert [resultado.id_original for resultado in ordenados] == ["dentro", "revisar", "fuera"]
    assert revisar.requiere_revision is True


def test_una_coincidencia_nueva_genera_aviso_al_responsable():
    notificador = NotificadorEnMemoria()
    avisos = AvisarNuevaCoincidencia(evaluador(), notificador).ejecutar(
        [busqueda()],
        extraccion(),
    )
    assert len(avisos) == 1
    assert avisos[0].destinatario == "rrhh-01"
    assert notificador.avisos == avisos
    assert notificador.estado == "SIMULADO_SIN_CANAL_CORPORATIVO"


def test_no_avisa_por_busqueda_cerrada_ni_por_no_coincidencia():
    notificador = NotificadorEnMemoria()
    caso = AvisarNuevaCoincidencia(evaluador(), notificador)
    assert caso.ejecutar([busqueda(abierta=False)], extraccion()) == []
    assert caso.ejecutar([busqueda(edad_maxima=25)], extraccion()) == []
    assert notificador.avisos == []


def test_maestro_de_perfiles_declara_dueno_y_estado():
    criterios = CriteriosPerfilYAML(RUTA)
    assert criterios.dueno_dato == "RRHH"
    assert criterios.estado == "PROPUESTA_SIN_VALIDAR"


@pytest.mark.parametrize("campo", ["id", "nombre", "definido_por"])
@pytest.mark.parametrize("valor", ["", None])
def test_rechaza_criterio_obligatorio_vacio_o_nulo(campo, valor):
    with pytest.raises(ValueError, match="no puede estar vacío"):
        busqueda(**{campo: valor})


@pytest.mark.parametrize(
    ("minima", "maxima"),
    [(-1, 30), (18, -1), (46, 45), (True, 45), (18, False)],
)
def test_rechaza_rangos_de_edad_invalidos(minima, maxima):
    with pytest.raises(ValueError):
        busqueda(edad_minima=minima, edad_maxima=maxima)
