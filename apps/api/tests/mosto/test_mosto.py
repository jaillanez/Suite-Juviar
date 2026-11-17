import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from suite_juviar.modulos.mosto.api.app import crear_router
from suite_juviar.modulos.mosto.application.servicios import GestionarMosto
from suite_juviar.modulos.mosto.domain.modelos import Etapa, precio_ajustado, promedio_ponderado
from suite_juviar.modulos.mosto.infrastructure.sqlite import MostoSQLite


class Reloj:
    def __init__(self):
        self.ahora = datetime(2026, 11, 17, 8, tzinfo=UTC)

    def __call__(self):
        return self.ahora


class Canal:
    def __init__(self, canal, resultado="enviado", falla=False):
        self.canal, self._resultado, self._falla, self.enviados = canal, resultado, falla, []

    def enviar(self, destino, asunto, texto):
        if self._falla:
            raise OSError("sin conexión")
        self.enviados.append((destino, texto))
        return self._resultado


def servicio(*canales, reloj=None):
    return GestionarMosto(MostoSQLite(Path(tempfile.mkdtemp()) / "m.sqlite3"), canales, reloj or Reloj())


def aprobada(s, tipo="sulfitado"):
    c = s.crear_compra("Mostos SA", "30712345678", tipo, 100000, 500, "comercial")
    s.cargar_analisis_oferta(c.id, {"azucar_gl": 229, "absorbancia_520": 0.3}, "lab")
    return s.decidir(c.id, Etapa.CALIDAD, True, "", "lab")


def test_formula_y_promedio():
    assert precio_ajustado(500, 228, 220) == pytest.approx(518.1818, rel=1e-4)
    assert promedio_ponderado([(10000, 230), (30000, 226)]) == 227


def test_rechazo_de_calidad_lo_puede_aprobar_produccion():
    s = servicio()
    c = s.crear_compra("Mostos SA", "30712345678", "sulfitado", 100000, 500, "comercial")
    with pytest.raises(ValueError, match="análisis"):
        s.decidir(c.id, Etapa.CALIDAD, False, "color", "lab")
    s.cargar_analisis_oferta(c.id, {"azucar_gl": 210, "absorbancia_520": 1.9}, "lab")
    with pytest.raises(ValueError, match="motivo"):
        s.decidir(c.id, Etapa.CALIDAD, False, "", "lab")
    with pytest.raises(ValueError, match="rechazó Calidad"):
        s.decidir(c.id, Etapa.PRODUCCION, True, "para mezcla", "jefe")
    assert s.decidir(c.id, Etapa.CALIDAD, False, "color alto", "lab").estado.value == "RECHAZADA_CALIDAD"
    assert s.decidir(c.id, Etapa.PRODUCCION, False, "no sirve", "jefe").estado.value == "RECHAZADA"
    with pytest.raises(ValueError, match="rechazó Calidad"):
        s.decidir(c.id, Etapa.PRODUCCION, True, "otra vez", "jefe")
    final = s.decidir(c.id, Etapa.COMERCIAL, True, "escasez de mercado", "comercial")
    assert final.estado.value == "APROBADA"
    assert [d.etapa.value for d in final.decisiones] == ["calidad", "produccion", "comercial"]


def test_viajes_liquidacion_con_margen_y_excepcion():
    s = servicio()
    c = aprobada(s)
    s.agregar_pileta(c.id, "P-1", 50000, {"azucar_gl": 229}, "lab")
    v1 = s.ingresar(c.id, "chimbas", "ab 123 cd", 20000, "bascula")
    assert v1.patente == "AB123CD"
    with pytest.raises(ValueError, match="ya está en planta"):
        s.ingresar(c.id, "chimbas", "AB123CD", 1000, "bascula")
    v2 = s.ingresar(c.id, "chimbas", "XY987ZW", 20000, "bascula")
    s.analizar_viaje(v1.id, {"azucar_gl": 230}, "lab")
    with pytest.raises(ValueError, match="sin análisis"):
        s.cerrar(c.id, "comercial")
    s.analizar_viaje(v2.id, {"azucar_gl": 228}, "lab")
    with pytest.raises(ValueError, match="no se descargaron"):
        s.cerrar(c.id, "comercial")
    with pytest.raises(ValueError, match="descarga"):
        s.mover(v1.id, "Concentrador", "", "jefe")
    for v in (v1, v2):
        s.descargar(v.id, "Pileta 4", "", "jefe")
    s.mover(v1.id, "Concentrador", "", "jefe")
    vista = s.ficha(c.id)
    assert vista["liquidacion"]["azucar_liquidada"] == 228  # 229 de promedio, 1 g/L de margen
    s.excepcion_margen(c.id, True, "acuerdo comercial")
    cerrada = s.cerrar(c.id, "comercial")
    assert cerrada.estado.value == "CERRADA"
    assert cerrada.liquidacion.azucar_liquidada == 229 and cerrada.liquidacion.margen_gl == 0
    assert cerrada.liquidacion.total == pytest.approx(500 * 229 / 220 * 40000, rel=1e-6)
    with pytest.raises(ValueError, match="cerrada"):
        s.analizar_viaje(v1.id, {"azucar_gl": 240}, "lab")
    with pytest.raises(ValueError, match="aprobada"):
        s.ingresar(c.id, "chimbas", "NUEVO11", 100, "bascula")


def test_alarma_de_mosto_virgen_una_vez_por_viaje():
    reloj = Reloj()
    correo, whatsapp = Canal("correo"), Canal("whatsapp", "encolado", falla=True)
    s = servicio(correo, whatsapp, reloj=reloj)
    c = aprobada(s, "virgen")
    sulfitado = aprobada(s)
    v = s.ingresar(c.id, "chimbas", "AA111BB", 25000, "bascula")
    s.ingresar(sulfitado.id, "chimbas", "CC222DD", 25000, "bascula")
    reloj.ahora += timedelta(hours=10)
    assert s.revisar_demoras() == []  # sin horas cargadas no hay alarma
    s.guardar_parametros(220, 1, 6, [{"nombre": "Producción", "correo": "prod@juviar.com.ar",
                                      "telefono": "5492645550000"}], "admin")
    avisos = s.revisar_demoras()
    assert len(avisos) == 1 and "AA111BB" in avisos[0].texto
    assert [(e.canal, e.resultado) for e in avisos[0].envios] == [("correo", "enviado"), ("whatsapp", "error")]
    assert s.revisar_demoras() == []
    assert s.vista_viaje(s.obtener_viaje(v.id))["demorado"] is True
    s.descargar(v.id, "Concentrador", "", "jefe")
    assert s.avisos()[0]["en_planta"] is False


def test_parametros_validan_destinatarios():
    s = servicio()
    with pytest.raises(ValueError, match="mail o el celular"):
        s.guardar_parametros(220, 1, 6, [{"nombre": "Ana"}], "admin")
    with pytest.raises(ValueError, match="horas"):
        s.guardar_parametros(220, 1, 0, [], "admin")


def cliente(perfil, ruta):
    app = FastAPI()
    app.include_router(crear_router(GestionarMosto(MostoSQLite(ruta)), "prueba"), prefix="/mosto")
    return TestClient(app, headers={"X-Perfil-Simulado": perfil, "X-Actor-Simulado": perfil.lower()})


def test_permisos_por_perfil():
    ruta = Path(tempfile.mkdtemp()) / "m.sqlite3"
    alta = {"proveedor": "Mostos SA", "cuit": "30712345678", "tipo": "sulfitado", "litros": 1000, "precio_base": 500}
    assert cliente("LABORATORIO", ruta).post("/mosto/compras", json=alta).status_code == 403
    compra = cliente("COMERCIAL", ruta).post("/mosto/compras", json=alta)
    assert compra.status_code == 201, compra.text
    cid = compra.json()["id"]
    assert cliente("COMERCIAL", ruta).post(f"/mosto/compras/{cid}/analisis", json={"azucar_gl": 220}).status_code == 403
    lab = cliente("LABORATORIO", ruta)
    assert lab.post(f"/mosto/compras/{cid}/analisis", json={"azucar_gl": 220}).status_code == 200
    assert lab.post(f"/mosto/compras/{cid}/calidad", json={"aprueba": True}).json()["estado"] == "APROBADA"
    viaje = {"compra_id": cid, "bodega": "chimbas", "patente": "AB123CD", "litros": 500}
    assert lab.post("/mosto/viajes", json=viaje).status_code == 403
    nuevo = cliente("BASCULA", ruta).post("/mosto/viajes", json=viaje)
    assert nuevo.status_code == 201
    vid = nuevo.json()["id"]
    assert cliente("BASCULA", ruta).post(f"/mosto/viajes/{vid}/descarga", json={"lugar": "P1"}).status_code == 403
    assert cliente("PRODUCCION", ruta).post(f"/mosto/viajes/{vid}/descarga", json={"lugar": "P1"}).status_code == 200
    assert cliente("COMERCIAL", ruta).get("/mosto/parametros").status_code == 403
    assert cliente("SUPERADMIN", ruta).get("/mosto/parametros").json()["azucar_referencia"] == 220
    assert cliente("RRHH", ruta).get("/mosto/compras").status_code == 403
