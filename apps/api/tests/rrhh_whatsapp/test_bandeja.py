"""Bandeja de RRHH: certificados y pedidos de EPP que el personal manda por WhatsApp (infra/042)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from suite_juviar.modulos.rrhh_whatsapp.api.app import crear_router
from suite_juviar.modulos.rrhh_whatsapp.application.servicios import SIN_LECTURA, BandejaRRHH
from suite_juviar.modulos.rrhh_whatsapp.domain.modelos import (
    Confirmacion,
    CVEntrante,
    MensajeEntrante,
)
from suite_juviar.modulos.rrhh_whatsapp.infrastructure.sqlite import BandejaCifradaMemoria
from suite_juviar.plataforma.identidad.api.dependencias import PERMISOS_POR_PERFIL

AHORA = datetime(2026, 11, 20, 12, tzinfo=UTC)
PDF = b"%PDF-1.4 certificado de prueba sin datos reales " + b"0" * 500
JPG = b"\xff\xd8\xff\xe0" + b"1" * 2000


def _certificado(id_="1", archivo=PDF, tipo="application/pdf"):
    return MensajeEntrante(id_, "5492640000000", "1210", "PRUEBA, EMPLEADO", "ENAV", "certificado",
                           "certificado médico", AHORA - timedelta(minutes=5), archivo, tipo, "cert.pdf")


def _epp(id_="2"):
    return MensajeEntrante(id_, "5492640000000", "1210", "PRUEBA, EMPLEADO", "ENAV", "epp",
                           "EPP: guantes talle 9", AHORA - timedelta(minutes=3))


class PuertaFalsa:
    def __init__(self):
        self.entrantes, self.confirmados, self.avisos = [], [], []
        self.respuestas: dict[str, Confirmacion] = {}
        self.cvs, self.cvs_confirmados, self.guardados, self.asignados = [], [], [], []
        self.falla_aviso = False

    def tomar_mensajes(self):
        return [m for m in self.entrantes if m.id not in self.confirmados]

    def confirmar_mensajes(self, ids):
        self.confirmados += ids

    def avisar_lectura(self, mensaje_id, texto, pide):
        if self.falla_aviso:
            raise OSError("sin base")
        self.avisos.append((mensaje_id, texto, pide))

    def confirmaciones(self, ids):
        return {i: r for i, r in self.respuestas.items() if i in ids}

    def tomar_cvs(self):
        return [c for c in self.cvs if c.id not in self.cvs_confirmados]

    def confirmar_cvs(self, ids):
        self.cvs_confirmados += ids

    def recorridos(self):
        return [{"id": 1, "sede": "chimbas", "nombre": "Rawson", "activo": True, "personas": 2}]

    def guardar_recorrido(self, recorrido_id, sede, nombre, activo, actor):
        self.guardados.append((recorrido_id, sede, nombre, activo, actor))
        return {"id": recorrido_id or 5, "sede": sede, "nombre": nombre, "activo": activo}

    def personal(self):
        return [{"telefono": "5492640000000", "legajo": "1210", "nombre": "PRUEBA, EMPLEADO", "empresa": "ENAV",
                 "recorrido_id": 1, "recorrido": "Rawson", "recorrido_sede": "chimbas"}]

    def asignar_recorrido(self, telefono, recorrido_id, actor):
        if recorrido_id == 99:
            raise ValueError("ese recorrido no existe o está inactivo")
        self.asignados.append((telefono, recorrido_id, actor))
        return {"telefono": telefono, "recorrido_id": recorrido_id}


class SaludFalsa:
    """Como GestionarSalud.cargar: el diagnóstico tiene que estar en el catálogo."""

    def __init__(self):
        self.catalogo = {"RESP-GRIPE", "TRAUMA-ESGUINCE"}
        self.cargados, self.auditoria = [], []

    def cargar(self, legajo, diagnostico_codigo, desde, hasta, dias, profesional, nombre_adjunto, contenido,
               resumen, tipo_accidente):
        if diagnostico_codigo not in self.catalogo:
            raise ValueError("El diagnóstico debe elegirse del catálogo médico.")
        if dias != (hasta - desde).days + 1:
            raise ValueError("Los días deben coincidir con las fechas.")
        self.cargados.append((legajo, diagnostico_codigo, desde.isoformat(), hasta.isoformat(), dias, profesional,
                              nombre_adjunto, contenido, resumen, tipo_accidente))
        return f"cert-{len(self.cargados)}"

    def auditar(self, actor, legajo, accion):
        self.auditoria.append((actor, legajo, accion))


def lector_con_datos(nombre, contenido, legajo):
    return {"dias_detectados": 3, "fecha_desde": "2026-11-18", "fecha_hasta": "2026-11-20",
            "profesional": "Dra. Prueba", "diagnostico_codigo": "RESP-GRIPE", "diagnostico_texto": "Gripe",
            "transcripcion": "texto completo", "resumen": "Reposo", "requiere_revision": True}


class Entorno:
    def __init__(self, lector=lector_con_datos, incorporar=None):
        self.puerta = PuertaFalsa()
        self.salud = SaludFalsa()
        self.repo = BandejaCifradaMemoria(b"0" * 32)
        self.adjuntos, self.lecturas, self.cvs = [], [], []
        self.reloj = AHORA

        def leer(nombre, contenido, legajo):
            self.lecturas.append((nombre, legajo))
            return lector(nombre, contenido, legajo)

        def adjuntar(legajo, nombre, contenido, actor):
            self.adjuntos.append((legajo, nombre, contenido, actor))
            return "adj-1"

        def incorporar_cv(cv):
            self.cvs.append(cv)
            return incorporar(cv) if incorporar else True

        self.servicio = BandejaRRHH(self.repo, self.puerta, leer, adjuntar, incorporar_cv,
                                    {"chimbas": "Chimbas"}, reloj=lambda: self.reloj, salud=self.salud)
        app = FastAPI()
        app.include_router(crear_router(self.servicio, "prueba"), prefix="/rrhh-whatsapp")
        self.app = app

    def cliente(self, perfil="RRHH"):
        return TestClient(self.app, headers={"X-Perfil-Simulado": perfil, "X-Actor-Simulado": f"{perfil.lower()}-1"})


def test_certificado_se_lee_y_se_le_pide_confirmacion_al_empleado():
    e = Entorno()
    e.puerta.entrantes = [_certificado()]
    [fila] = e.cliente().get("/rrhh-whatsapp/mensajes").json()
    assert fila["estado"] == "PENDIENTE" and fila["legajo"] == "1210" and fila["con_archivo"]
    # Los datos leídos quedan precargados para RRHH; el diagnóstico no (es de Salud).
    assert fila["lectura"]["dias_detectados"] == 3 and fila["lectura"]["fecha_desde"] == "2026-11-18"
    assert "diagnostico_codigo" not in fila["lectura"] and "transcripcion" not in fila["lectura"]
    assert "resumen" not in fila["lectura"]  # puede traer el diagnóstico: sólo en Salud
    [(mensaje_id, texto, pide)] = e.puerta.avisos
    assert mensaje_id == "1" and pide and "Días: 3" in texto and "18/11/2026" in texto
    assert "1 = Sí, es correcto" in texto and "2 = No" in texto
    assert fila["confirmacion"] == "esperando" and e.puerta.confirmados == ["1"]
    assert e.lecturas == [("certificado-1.pdf", "1210")]


def test_lector_sin_datos_no_pide_confirmacion():
    e = Entorno(lector=lambda *_: {"resumen": "", "dias_detectados": None, "texto_detectado": False})
    e.puerta.entrantes = [_certificado()]
    [fila] = e.cliente().get("/rrhh-whatsapp/mensajes").json()
    assert e.puerta.avisos == [("1", SIN_LECTURA, False)]
    assert fila["confirmacion"] == "sin_pedir" and fila["estado"] == "PENDIENTE"


def test_si_el_lector_falla_queda_en_la_bandeja_con_los_campos_vacios():
    def roto(*_):
        raise RuntimeError("La IA no pudo leer el certificado.")

    e = Entorno(lector=roto)
    e.puerta.entrantes = [_certificado()]
    [fila] = e.cliente().get("/rrhh-whatsapp/mensajes").json()
    assert fila["lectura"] == {} and fila["lectura_error"] and fila["estado"] == "PENDIENTE"
    assert e.puerta.avisos == [("1", SIN_LECTURA, False)]


def test_si_no_se_puede_avisar_se_reintenta_en_la_proxima_sincronizacion():
    e = Entorno()
    e.puerta.entrantes = [_certificado()]
    e.puerta.falla_aviso = True
    e.servicio.sincronizar()
    assert e.puerta.confirmados == ["1"] and e.puerta.avisos == []
    e.puerta.falla_aviso = False
    e.servicio.sincronizar()
    assert len(e.puerta.avisos) == 1 and len(e.lecturas) == 1  # no se vuelve a leer


def test_respuestas_del_empleado_confirmado_no_coincide_y_sin_respuesta():
    e = Entorno()
    e.puerta.entrantes = [_certificado("1"), _certificado("3"), _certificado("4")]
    e.servicio.sincronizar()
    vence = AHORA + timedelta(hours=24)
    e.puerta.respuestas = {
        "1": Confirmacion("confirmado", vence, "", AHORA),
        "3": Confirmacion("no_coincide", vence, "son 5 días", AHORA),
        "4": Confirmacion("esperando", vence, "", None),
    }
    filas = {f["id"]: f for f in e.cliente().get("/rrhh-whatsapp/mensajes").json()}
    assert filas["1"]["confirmacion"] == "confirmado"
    assert filas["3"]["confirmacion"] == "no_coincide" and filas["3"]["correccion"] == "son 5 días"
    assert filas["4"]["confirmacion"] == "esperando"
    assert all(f["estado"] == "PENDIENTE" for f in filas.values())  # nada pasa solo al legajo
    e.reloj = AHORA + timedelta(hours=25)  # venció la espera sin respuesta
    filas = {f["id"]: f for f in e.cliente().get("/rrhh-whatsapp/mensajes").json()}
    assert filas["4"]["confirmacion"] == "sin_confirmar"


def test_pasar_al_legajo_guarda_el_archivo_como_adjunto_y_deja_quien():
    e = Entorno()
    e.puerta.entrantes = [_certificado()]
    c = e.cliente()
    c.get("/rrhh-whatsapp/mensajes")
    malo = c.post("/rrhh-whatsapp/mensajes/1/legajo", json={"dias": 4, "desde": "2026-11-18", "hasta": "2026-11-20"})
    assert malo.status_code == 400 and "3" in malo.json()["detail"]
    r = c.post("/rrhh-whatsapp/mensajes/1/legajo", json={
        "dias": 3, "desde": "2026-11-18", "hasta": "2026-11-20", "profesional": "Dra. Prueba",
        "nombre": "Certificado noviembre"})
    assert r.status_code == 200, r.text
    fila = r.json()
    assert fila["estado"] == "EN_LEGAJO" and fila["resuelto_por"] == "rrhh-1" and fila["adjunto_id"] == "adj-1"
    assert fila["datos_confirmados"]["dias"] == 3
    assert e.adjuntos == [("1210", "Certificado noviembre.pdf", PDF, "rrhh-1")]
    assert fila["salud"] == "CARGADO"
    assert c.post("/rrhh-whatsapp/mensajes/1/legajo", json={}).status_code == 400  # ya resuelto


def test_pedido_de_epp_se_atiende_con_nota_y_no_pasa_al_legajo():
    e = Entorno()
    e.puerta.entrantes = [_epp()]
    c = e.cliente()
    [fila] = c.get("/rrhh-whatsapp/mensajes").json()
    assert fila["tipo"] == "epp" and not fila["con_archivo"] and e.puerta.avisos == []
    assert c.post("/rrhh-whatsapp/mensajes/2/legajo", json={}).status_code == 400
    r = c.post("/rrhh-whatsapp/mensajes/2/atender", json={"nota": "Se entregaron en depósito"}).json()
    assert r["estado"] == "ATENDIDO" and r["nota"] == "Se entregaron en depósito" and r["resuelto_por"] == "rrhh-1"
    assert r["resuelto_en"]


def test_descartar_exige_motivo_y_deja_quien():
    e = Entorno()
    e.puerta.entrantes = [_certificado()]
    c = e.cliente()
    c.get("/rrhh-whatsapp/mensajes")
    assert c.post("/rrhh-whatsapp/mensajes/1/descartar", json={"motivo": ""}).status_code == 422
    assert c.post("/rrhh-whatsapp/mensajes/1/descartar", json={"motivo": "   "}).status_code == 400
    r = c.post("/rrhh-whatsapp/mensajes/1/descartar", json={"motivo": "Foto ilegible, se pidió de nuevo"}).json()
    assert r["estado"] == "DESCARTADO" and r["resuelto_por"] == "rrhh-1"
    assert c.post("/rrhh-whatsapp/mensajes/1/atender", json={}).status_code == 400


def test_el_archivo_se_sirve_y_se_guarda_cifrado():
    e = Entorno()
    e.puerta.entrantes = [_certificado(archivo=JPG, tipo="image/jpeg")]
    c = e.cliente()
    c.get("/rrhh-whatsapp/mensajes")
    r = c.get("/rrhh-whatsapp/mensajes/1/archivo")
    assert r.status_code == 200 and r.content == JPG and r.headers["content-type"] == "image/jpeg"
    assert JPG not in e.repo.bytes_persistidos("1") and b"PRUEBA" not in e.repo.bytes_persistidos("1")


@pytest.mark.parametrize("perfil", ["MEDICO", "BODEGA", "MANTENIMIENTO", "DEPOSITO"])
def test_solo_rrhh_ve_la_bandeja(perfil):
    e = Entorno()
    assert e.cliente(perfil).get("/rrhh-whatsapp/mensajes").status_code == 403
    assert e.cliente(perfil).post("/rrhh-whatsapp/mensajes/1/descartar", json={"motivo": "x"}).status_code == 403
    assert e.cliente(perfil).get("/rrhh-whatsapp/recorridos").status_code == 403
    assert e.cliente("RRHH").get("/rrhh-whatsapp/mensajes").status_code == 200
    assert e.cliente("SUPERADMIN").get("/rrhh-whatsapp/mensajes").status_code == 200


def test_control_negativo_rrhh_sin_el_permiso_no_entra(monkeypatch):
    monkeypatch.setitem(PERMISOS_POR_PERFIL, "RRHH", PERMISOS_POR_PERFIL["RRHH"] - {"rrhh.bandeja.gestionar"})
    assert Entorno().cliente("RRHH").get("/rrhh-whatsapp/mensajes").status_code == 403


def test_recorridos_del_micro():
    e = Entorno()
    c = e.cliente()
    assert c.get("/rrhh-whatsapp/recorridos").json()[0]["sede_nombre"] == "Chimbas"
    assert c.post("/rrhh-whatsapp/recorridos", json={"sede": "marte", "nombre": "Rawson"}).status_code == 409
    r = c.post("/rrhh-whatsapp/recorridos", json={"sede": "chimbas", "nombre": "  Rawson   centro "})
    assert r.status_code == 201 and e.puerta.guardados == [(None, "chimbas", "Rawson centro", True, "rrhh-1")]
    c.put("/rrhh-whatsapp/recorridos/5", json={"sede": "chimbas", "nombre": "Rawson", "activo": False})
    assert e.puerta.guardados[-1] == (5, "chimbas", "Rawson", False, "rrhh-1")


def test_cv_por_whatsapp_se_incorpora_y_recien_entonces_se_confirma():
    fallas = {"9"}

    def incorporar(cv):
        if cv.id in fallas:
            raise OSError("disco lleno")
        return True

    e = Entorno(incorporar=incorporar)
    e.puerta.cvs = [CVEntrante("8", "5492645555555", "cv.pdf", PDF, "application/pdf", AHORA),
                    CVEntrante("9", "5492646666666", "cv.jpg", JPG, "image/jpeg", AHORA)]
    e.servicio.sincronizar()
    assert e.puerta.cvs_confirmados == ["8"]  # el que falló queda en la DMZ para la próxima
    fallas.clear()
    e.servicio.sincronizar()
    assert e.puerta.cvs_confirmados == ["8", "9"]


# --- El certificado también va a Salud (el diagnóstico es secreto médico) ---------------------

DATOS_RRHH = {"dias": 3, "desde": "2026-11-18", "hasta": "2026-11-20", "profesional": "Dra. Prueba"}


def _sin_diagnostico(*_):
    return {"dias_detectados": 3, "fecha_desde": "2026-11-18", "fecha_hasta": "2026-11-20",
            "profesional": "Dra. Prueba", "resumen": "Reposo"}


def _pasar(e, datos=DATOS_RRHH, mensaje_id="1"):
    c = e.cliente()
    c.get("/rrhh-whatsapp/mensajes")
    r = c.post(f"/rrhh-whatsapp/mensajes/{mensaje_id}/legajo", json=datos)
    assert r.status_code == 200, r.text
    return r


def _sin_diagnostico_en(respuesta):
    texto = respuesta.text
    for prohibido in ("RESP-GRIPE", "Gripe", "diagnostico", "Reposo", "lectura_salud", "salud_motivo", "motivo"):
        assert prohibido not in texto, prohibido


def test_con_diagnostico_del_catalogo_se_carga_solo_en_salud():
    e = Entorno()
    e.puerta.entrantes = [_certificado()]
    r = _pasar(e)
    assert r.json()["estado"] == "EN_LEGAJO" and r.json()["salud"] == "CARGADO"
    [cargado] = e.salud.cargados
    assert cargado[:6] == ("1210", "RESP-GRIPE", "2026-11-18", "2026-11-20", 3, "Dra. Prueba")
    assert cargado[7] == PDF and cargado[8] == "Reposo"
    assert ("rrhh-1", "1210", "CARGA_CERTIFICADO_WHATSAPP_AUTOMATICA") in e.salud.auditoria
    assert len(e.adjuntos) == 1  # y además en el legajo
    assert e.cliente("MEDICO").get("/rrhh-whatsapp/salud/pendientes").json() == []


def test_sin_dias_salen_de_las_fechas_que_confirmo_rrhh():
    e = Entorno()
    e.puerta.entrantes = [_certificado()]
    r = _pasar(e, {"desde": "2026-11-18", "hasta": "2026-11-20", "profesional": "Dra. Prueba"})
    assert r.json()["salud"] == "CARGADO" and e.salud.cargados[0][4] == 3


def test_sin_diagnostico_queda_pendiente_y_el_medico_lo_completa():
    e = Entorno(lector=_sin_diagnostico)
    e.puerta.entrantes = [_certificado()]
    r = _pasar(e)
    assert r.json()["estado"] == "EN_LEGAJO" and r.json()["salud"] == "PENDIENTE" and e.salud.cargados == []
    medico = e.cliente("MEDICO")
    [p] = medico.get("/rrhh-whatsapp/salud/pendientes").json()
    assert p["legajo"] == "1210" and p["datos_confirmados"]["dias"] == 3 and p["diagnostico_codigo"] == ""
    assert "diagnóstico" in p["motivo"] and p["resumen"] == "Reposo" and p["pasado_por"] == "rrhh-1"
    archivo = medico.get("/rrhh-whatsapp/salud/pendientes/1/archivo")
    assert archivo.status_code == 200 and archivo.content == PDF
    malo = medico.post("/rrhh-whatsapp/salud/pendientes/1/cargar", json={"diagnostico_codigo": "INVENTADO"})
    assert malo.status_code == 400 and "catálogo" in malo.json()["detail"]
    ok = medico.post("/rrhh-whatsapp/salud/pendientes/1/cargar", json={"diagnostico_codigo": "trauma-esguince"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["salud"] == "CARGADO" and ok.json()["salud_por"] == "medico-1"
    assert e.salud.cargados[0][:6] == ("1210", "TRAUMA-ESGUINCE", "2026-11-18", "2026-11-20", 3, "Dra. Prueba")
    acciones = [a for a in e.salud.auditoria if a[0] == "medico-1"]
    assert [a[2] for a in acciones] == ["CONSULTA_PENDIENTES_WHATSAPP", "CONSULTA_ADJUNTO_WHATSAPP",
                                        "CARGA_CERTIFICADO_WHATSAPP"]
    assert medico.get("/rrhh-whatsapp/salud/pendientes").json() == []
    assert medico.post("/rrhh-whatsapp/salud/pendientes/1/cargar",
                       json={"diagnostico_codigo": "RESP-GRIPE"}).status_code == 404  # ya cargado
    [fila] = e.cliente().get("/rrhh-whatsapp/mensajes?estado=EN_LEGAJO").json()
    assert fila["salud"] == "CARGADO"


def test_diagnostico_leido_fuera_del_catalogo_queda_pendiente_y_el_medico_lo_ve():
    e = Entorno(lector=lambda *_: {**lector_con_datos(None, None, None), "diagnostico_codigo": "J11"})
    e.puerta.entrantes = [_certificado()]
    assert _pasar(e).json()["salud"] == "PENDIENTE"
    [p] = e.cliente("MEDICO").get("/rrhh-whatsapp/salud/pendientes").json()
    assert p["diagnostico_codigo"] == "J11" and p["diagnostico_texto"] == "Gripe" and "catálogo" in p["motivo"]


def test_sin_fechas_queda_pendiente_y_el_medico_las_completa():
    e = Entorno()
    e.puerta.entrantes = [_certificado()]
    assert _pasar(e, {"profesional": "Dra. Prueba"}).json()["salud"] == "PENDIENTE"
    medico = e.cliente("MEDICO")
    sin_fechas = medico.post("/rrhh-whatsapp/salud/pendientes/1/cargar", json={"diagnostico_codigo": "RESP-GRIPE"})
    assert sin_fechas.status_code == 400 and "fecha" in sin_fechas.json()["detail"]
    ok = medico.post("/rrhh-whatsapp/salud/pendientes/1/cargar", json={
        "diagnostico_codigo": "RESP-GRIPE", "desde": "2026-11-18", "hasta": "2026-11-19"})
    assert ok.status_code == 200 and e.salud.cargados[0][4] == 2


def test_rrhh_nunca_recibe_el_diagnostico():
    e = Entorno(lector=lambda *_: {**lector_con_datos(None, None, None), "diagnostico_codigo": "J11"})
    e.puerta.entrantes = [_certificado("1"), _certificado("3")]
    c = e.cliente()
    _sin_diagnostico_en(c.get("/rrhh-whatsapp/mensajes"))
    _sin_diagnostico_en(c.post("/rrhh-whatsapp/mensajes/1/legajo", json=DATOS_RRHH))  # queda pendiente
    e.salud.catalogo.add("J11")
    _sin_diagnostico_en(c.post("/rrhh-whatsapp/mensajes/3/legajo", json=DATOS_RRHH))  # se carga solo
    _sin_diagnostico_en(c.get("/rrhh-whatsapp/mensajes"))
    _sin_diagnostico_en(c.get("/rrhh-whatsapp/mensajes?estado=EN_LEGAJO"))
    estados = {f["id"]: f["salud"] for f in c.get("/rrhh-whatsapp/mensajes").json()}
    assert estados == {"1": "PENDIENTE", "3": "CARGADO"}
    # Lo que se guarda para Salud está cifrado como el resto de la bandeja.
    assert b"J11" not in e.repo.bytes_persistidos("1") and b"Gripe" not in e.repo.bytes_persistidos("1")


@pytest.mark.parametrize("perfil", ["RRHH", "BODEGA", "MANTENIMIENTO", "DEPOSITO"])
def test_solo_el_medico_completa_salud(perfil):
    e = Entorno(lector=_sin_diagnostico)
    e.puerta.entrantes = [_certificado()]
    _pasar(e)
    c = e.cliente(perfil)
    assert c.get("/rrhh-whatsapp/salud/pendientes").status_code == 403
    assert c.get("/rrhh-whatsapp/salud/pendientes/1/archivo").status_code == 403
    assert c.post("/rrhh-whatsapp/salud/pendientes/1/cargar",
                  json={"diagnostico_codigo": "RESP-GRIPE"}).status_code == 403
    assert e.salud.cargados == []
    assert e.cliente("MEDICO").post("/rrhh-whatsapp/salud/pendientes/1/cargar",
                                    json={"diagnostico_codigo": "RESP-GRIPE"}).status_code == 200


def test_si_salud_falla_el_legajo_queda_y_se_completa_despues():
    e = Entorno()

    def caida(*_):
        raise OSError("disco lleno")

    e.salud.cargar = caida
    e.puerta.entrantes = [_certificado()]
    r = _pasar(e)
    assert r.json()["estado"] == "EN_LEGAJO" and r.json()["salud"] == "PENDIENTE" and len(e.adjuntos) == 1


# --- RRHH asigna el recorrido del micro --------------------------------------------------------

def test_rrhh_asigna_el_recorrido_a_cada_empleado():
    e = Entorno()
    c = e.cliente()
    [p] = c.get("/rrhh-whatsapp/personal").json()
    assert p["recorrido_id"] == 1 and p["recorrido_sede_nombre"] == "Chimbas"
    assert set(p) == {"telefono", "legajo", "nombre", "empresa", "recorrido_id", "recorrido", "recorrido_sede",
                      "recorrido_sede_nombre"}
    r = c.put("/rrhh-whatsapp/personal/5492640000000/recorrido", json={"recorrido_id": 2})
    assert r.status_code == 200 and e.puerta.asignados == [("5492640000000", 2, "rrhh-1")]
    assert c.put("/rrhh-whatsapp/personal/5492640000000/recorrido", json={"recorrido_id": None}).status_code == 200
    assert e.puerta.asignados[-1] == ("5492640000000", None, "rrhh-1")
    assert c.put("/rrhh-whatsapp/personal/5492640000000/recorrido", json={"recorrido_id": 99}).status_code == 409
    assert c.put("/rrhh-whatsapp/personal/no-es-un-celular/recorrido", json={}).status_code == 422


def test_rrhh_no_cambia_otros_datos_del_personal_por_la_asignacion():
    e = Entorno()
    c = e.cliente()
    r = c.put("/rrhh-whatsapp/personal/5492640000000/recorrido",
              json={"recorrido_id": 2, "legajo": "9999", "tipo": "mando_medio", "activo": False})
    assert r.status_code == 200 and e.puerta.asignados == [("5492640000000", 2, "rrhh-1")]  # el resto se ignora
    for metodo, ruta in (("post", "/rrhh-whatsapp/personal"), ("delete", "/rrhh-whatsapp/personal/5492640000000"),
                         ("post", "/rrhh-whatsapp/personal/5492640000000/baja")):
        assert getattr(c, metodo)(ruta).status_code in {404, 405}


@pytest.mark.parametrize("perfil", ["MEDICO", "BODEGA", "MANTENIMIENTO", "DEPOSITO"])
def test_solo_rrhh_asigna_recorridos(perfil):
    e = Entorno()
    c = e.cliente(perfil)
    assert c.get("/rrhh-whatsapp/personal").status_code == 403
    assert c.put("/rrhh-whatsapp/personal/5492640000000/recorrido", json={"recorrido_id": 2}).status_code == 403
    assert e.puerta.asignados == []
