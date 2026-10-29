import base64
import json
from dataclasses import asdict
from datetime import date

import pytest
from fastapi.testclient import TestClient

from suite_juviar.modulos.salud.api.app import crear_app
from suite_juviar.modulos.salud.application.servicios import GestionarSalud
from suite_juviar.modulos.salud.domain.modelos import (
    AccesoSaludDenegado,
    FuenteSimuladaEnProduccion,
    ReporteNominadoProhibido,
)
from suite_juviar.modulos.salud.infrastructure.simulados import (
    AdjuntosSaludCifradosMemoria,
    CatalogoDiagnosticoSimulado,
    FuenteLaboralSimulada,
    SaludMemoria,
)
from suite_juviar.plataforma.identidad.api.dependencias import PERMISOS_POR_PERFIL


def servicio():
    return GestionarSalud(
        CatalogoDiagnosticoSimulado(), SaludMemoria(),
        AdjuntosSaludCifradosMemoria(b"0" * 32), FuenteLaboralSimulada(),
    )


def cargar(s, legajo="10", codigo="MUESTRA-RESP", desde=date(2026, 6, 1)):
    return s.cargar(
        legajo, codigo, desde, desde, 1, "Dra. Prueba", "escaneo.pdf", b"PDF original",
    )


def cuerpo(legajo="10", codigo="MUESTRA-RESP"):
    return {
        "legajo": legajo, "diagnostico_codigo": codigo,
        "desde": "2026-06-01", "hasta": "2026-06-03", "dias": 3,
        "profesional": "Dra. Prueba", "adjunto_nombre": "escaneo.pdf",
        "adjunto_base64": base64.b64encode(b"PDF original").decode(),
    }


def test_rrhh_general_sin_rol_y_rol_nulo_no_ven_diagnostico():
    s = servicio()
    certificado = cargar(s)
    for rol in ("RRHH", "", None):
        with pytest.raises(AccesoSaludDenegado):
            s.consultar(certificado.id, "actor", rol)


def test_catalogo_es_jerarquico_simulado_y_del_servicio_medico():
    cliente = TestClient(crear_app(servicio()), headers={"X-Perfil-Simulado": "MEDICO"})
    respuesta = cliente.get("/catalogo")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["fuente_simulada"] is True
    assert datos["dueno_dato"] == "Servicio Médico"
    assert any(x["padre_codigo"] == "MUESTRA" for x in datos["items"])


def test_certificado_completo_conserva_adjunto_original_cifrado():
    s = servicio()
    certificado = cargar(s)
    assert certificado.dias == 1
    assert certificado.profesional == "Dra. Prueba"
    assert s.adjuntos.obtener(certificado.adjunto_id).contenido == b"PDF original"
    assert b"PDF original" not in s.adjuntos.bytes_persistidos(certificado.adjunto_id)


def test_lectura_medica_y_consulta_de_bitacora_se_auditan_sin_diagnostico():
    s = servicio()
    certificado = cargar(s)
    s.consultar(certificado.id, "medico-1", "MEDICO")
    filas_antes = s.bitacora("medico-auditor", usuario="medico-1", legajo="10")
    assert filas_antes[0].accion == "CONSULTA_CERTIFICADO"
    assert s.repositorio.consultas[-1].accion == "CONSULTA_BITACORA"
    serializado = json.dumps([asdict(x) for x in s.repositorio.consultas], default=str).casefold()
    assert "muestra-resp" not in serializado
    assert "diagnostico" not in serializado


def test_reporte_suprime_grupos_unitarios_y_nunca_es_nominado():
    s = servicio()
    cargar(s, "10")
    assert s.reporte_agregado()["por_diagnostico"] == []
    cargar(s, "11")
    reporte = s.reporte_agregado()
    assert reporte["por_diagnostico"][0]["personas"] == 2
    assert reporte["nominado"] is False
    with pytest.raises(ReporteNominadoProhibido):
        s.reporte_agregado(incluir_personas=True)


def test_articulo_208_es_preliminar_y_no_admite_imprimir_o_exportar():
    s = servicio()
    aviso = s.aviso_articulo_208("10")
    assert aviso["leyenda"] == "Preliminar: antigüedad y cargas de familia simuladas, sin conexión a Nexus"
    assert aviso["imprimible"] is False and aviso["exportable"] is False
    cliente = TestClient(crear_app(s), headers={"X-Perfil-Simulado": "MEDICO"})
    assert cliente.get("/articulo-208/10/imprimir").status_code == 409
    assert cliente.get("/articulo-208/10/exportar").status_code == 409


def test_bitacora_api_es_inmutable_y_la_consulta_no_expone_diagnostico():
    s = servicio()
    cargar(s)
    s.auditar("medico-1", "10", "CARGA_CERTIFICADO")
    cliente = TestClient(crear_app(s), headers={"X-Perfil-Simulado": "MEDICO"})
    inicial = cliente.get("/bitacora").json()
    identificador = inicial[0]["id"]
    assert "diagnostico" not in json.dumps(inicial).casefold()
    assert cliente.patch(f"/bitacora/{identificador}", json={"accion": "ALTERADA"}).status_code == 405
    assert cliente.delete(f"/bitacora/{identificador}").status_code == 405
    assert s.repositorio.listar_auditoria()[0].accion == "CARGA_CERTIFICADO"


def test_marca_visible_y_produccion_rechaza_catalogo_simulado():
    s = servicio()
    assert "DATOS SIMULADOS — SIN VALIDEZ" in TestClient(
        crear_app(s), headers={"X-Perfil-Simulado": "MEDICO"}
    ).get("/").text
    with pytest.raises(FuenteSimuladaEnProduccion):
        crear_app(s, "produccion")


def test_api_rechaza_carga_y_consulta_de_rrhh():
    cliente = TestClient(crear_app(servicio()))
    assert cliente.post("/certificados", json=cuerpo()).status_code == 401
    assert cliente.post("/certificados", json=cuerpo(), headers={"X-Perfil-Simulado": "RRHH"}).status_code == 403
    creado = cliente.post("/certificados", json=cuerpo(), headers={"X-Perfil-Simulado": "MEDICO"})
    assert creado.status_code == 200
    identificador = creado.json()["id"]
    assert cliente.get(f"/certificados/{identificador}").status_code == 401
    assert cliente.get(f"/certificados/{identificador}", headers={"X-Perfil-Simulado": "RRHH"}).status_code == 403


def test_control_negativo_detecta_si_se_aflojan_permisos_de_rrhh(monkeypatch):
    cliente = TestClient(crear_app(servicio()))
    assert cliente.get("/catalogo", headers={"X-Perfil-Simulado": "RRHH"}).status_code == 403
    permisos_mutados = PERMISOS_POR_PERFIL["RRHH"] | {
        "salud.diagnostico.leer", "salud.certificado.gestionar",
    }
    monkeypatch.setitem(PERMISOS_POR_PERFIL, "RRHH", permisos_mutados)
    assert cliente.get("/catalogo", headers={"X-Perfil-Simulado": "RRHH"}).status_code == 200
    assert cliente.post("/certificados", json=cuerpo(), headers={"X-Perfil-Simulado": "RRHH"}).status_code == 200


class _PersonasDePrueba:
    def buscar_texto(self, texto):
        from suite_juviar.modulos.legajo.domain.modelos import PersonaLegajo
        return [PersonaLegajo("10", "Pérez, Ana", "ENAV", "Bodega", "Operaria")]


def test_buscar_personas_exige_permiso_propio_y_devuelve_solo_lo_necesario(monkeypatch):
    s = GestionarSalud(
        CatalogoDiagnosticoSimulado(), SaludMemoria(),
        AdjuntosSaludCifradosMemoria(b"0" * 32), FuenteLaboralSimulada(), _PersonasDePrueba(),
    )
    cliente = TestClient(crear_app(s), headers={"X-Perfil-Simulado": "MEDICO"})
    respuesta = cliente.get("/personas", params={"q": "Pérez"})
    assert respuesta.status_code == 200
    assert respuesta.json() == [{
        "legajo": "10", "nombre_completo": "Pérez, Ana",
        "empresa": "ENAV", "sector": "Bodega", "puesto": "Operaria",
    }]
    sin_busqueda = PERMISOS_POR_PERFIL["MEDICO"] - {"salud.persona.buscar"}
    monkeypatch.setitem(PERMISOS_POR_PERFIL, "MEDICO", sin_busqueda)
    assert cliente.get("/personas", params={"q": "Pérez"}).status_code == 403


def test_articulo_208_no_expone_antiguedad_ni_cargas_de_familia():
    aviso = servicio().aviso_articulo_208("10")
    assert "meses_remunerados" in aviso
    assert "antiguedad_anios" not in aviso and "cargas_familia" not in aviso


def test_ia_externa_se_registra_y_en_produccion_requiere_autorizacion(monkeypatch):
    from suite_juviar.modulos.salud.application import lector_certificados

    enviados = []
    monkeypatch.setenv("SJ_SALUD_IA_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(
        lector_certificados, "_leer_con_deepseek",
        lambda nombre, contenido, clave: enviados.append(nombre) or {"motor": "deepseek"},
    )
    monkeypatch.setattr(lector_certificados, "_leer_imagen", lambda contenido, extension: "")
    imagen = {"adjunto_nombre": "certificado.jpg",
              "adjunto_base64": base64.b64encode(b"imagen").decode()}

    s = servicio()
    cliente = TestClient(crear_app(s), headers={"X-Perfil-Simulado": "MEDICO"})
    assert cliente.post("/certificados/analizar", json=imagen).status_code == 200
    assert enviados == ["certificado.jpg"]
    assert s.repositorio.listar_auditoria()[-1].accion == "ENVIO_CERTIFICADO_A_IA_EXTERNA_DEEPSEEK"

    s.catalogo.simulada = False
    produccion = TestClient(crear_app(s, "produccion"), headers={"X-Perfil-Simulado": "MEDICO"})
    assert produccion.post("/certificados/analizar", json=imagen).status_code == 200
    assert enviados == ["certificado.jpg"]
    assert s.repositorio.listar_auditoria()[-1].accion == "ANALISIS_CERTIFICADO"

    monkeypatch.setenv("SJ_SALUD_IA_EXTERNA_AUTORIZADA", "si")
    autorizada = TestClient(crear_app(s, "produccion"), headers={"X-Perfil-Simulado": "MEDICO"})
    assert autorizada.post("/certificados/analizar", json=imagen).status_code == 200
    assert enviados == ["certificado.jpg", "certificado.jpg"]
