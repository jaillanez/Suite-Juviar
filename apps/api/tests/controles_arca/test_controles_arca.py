import base64
import io
import tempfile
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from fastapi.testclient import TestClient

from suite_juviar.modulos.controles_arca.api.app import crear_router
from suite_juviar.modulos.controles_arca.application.servicios import GestionarControles
from suite_juviar.modulos.controles_arca.domain.modelos import (
    AccesoARCA,
    Constancia,
    Constatacion,
    ErrorARCA,
    Estado,
    Padron,
    cuit_valido,
    evaluar_apocrifa,
    evaluar_constancia,
    evaluar_constatacion,
    evaluar_rg18,
    nombre_pdf,
)
from suite_juviar.modulos.controles_arca.infrastructure.arca import (
    ConectorARCAWeb,
    armar_tra,
    firmar_tra,
    leer_constancia,
    leer_constatacion,
)
from suite_juviar.modulos.controles_arca.infrastructure.certificados import CertificadosRSA
from suite_juviar.modulos.controles_arca.infrastructure.cifrado import CifradorARCA
from suite_juviar.modulos.controles_arca.infrastructure.padrones import leer_apocrifas, leer_rg18
from suite_juviar.modulos.controles_arca.infrastructure.pdf import ConstanciaPDF
from suite_juviar.modulos.controles_arca.infrastructure.sqlite import ControlesSQLite
from suite_juviar.plataforma.identidad.api.dependencias import PERMISOS_POR_PERFIL

PROVEEDOR = "30693135679"
APOCRIFO = "30703948983"
AGENTE = "30500010912"
ENAV = "30546689979"
REPRESENTANTE = "20172238832"
CAE = "71234567890123"


class Reloj:
    def __init__(self):
        self.ahora = datetime(2026, 11, 18, 13, tzinfo=UTC)

    def __call__(self):
        return self.ahora


class Conector:
    def __init__(self, constancia=None, constatacion=None, falla=None):
        self._constancia = constancia or Constancia(True, "Proveedor SA", "ACTIVO", ("IVA", "GANANCIAS SOCIEDADES"))
        self._constatacion = constatacion or Constatacion("A")
        self._falla = falla
        self.llamadas = []

    def constancia(self, acceso, cuit_representada, cuit):
        self.llamadas.append(("constancia", acceso.ambiente, cuit_representada, cuit, bool(acceso.clave_pem)))
        if self._falla:
            raise self._falla
        return self._constancia

    def constatar(self, acceso, cuit_representada, factura, cuit_receptor):
        self.llamadas.append(("constatar", acceso.ambiente, cuit_representada, factura.numero, bool(acceso.clave_pem)))
        self.receptor = cuit_receptor
        if self._falla:
            raise self._falla
        return self._constatacion


class Descargas:
    def __init__(self):
        self.bajadas = []

    def descargar(self, nombre, url):
        self.bajadas.append(nombre)
        if nombre == "apocrifas":
            return "18/11/2026", {APOCRIFO: (("08/11/2005", "08/11/2005", ""),)}
        return "17/11/2026 02:11", {AGENTE: (("AGENTE SA", "01/11/2019", "", "B"),)}


def ca_de_prueba():
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CA de prueba")])
    return clave, nombre


def firmar_csr(csr_pem, cuit=None, vence=None):
    """Hace de ARCA: firma el pedido y devuelve el .crt."""
    ca, nombre = ca_de_prueba()
    csr = x509.load_pem_x509_csr(csr_pem.encode())
    sujeto = csr.subject if cuit is None else x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "otro"), x509.NameAttribute(NameOID.SERIAL_NUMBER, f"CUIT {cuit}")])
    ahora = datetime(2026, 11, 18, tzinfo=UTC)
    certificado = (x509.CertificateBuilder().subject_name(sujeto).issuer_name(nombre)
                   .public_key(csr.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(ahora - timedelta(days=1)).not_valid_after(vence or ahora + timedelta(days=700))
                   .sign(ca, hashes.SHA256()))
    return certificado.public_bytes(serialization.Encoding.PEM).decode()


def servicio(conector=None, reloj=None, ruta=None, descargas=None):
    repo = ControlesSQLite(ruta or Path(tempfile.mkdtemp()) / "c.sqlite3")
    return GestionarControles(repo, ConstanciaPDF(), descargas or Descargas(), conector, CertificadosRSA(),
                              CifradorARCA.desde_secreto("secreto-de-prueba"), reloj or Reloj())


def parametros(s, **cambios):
    datos = {**s.vista_parametros(), "cuit_empresas": {"ENAV": ENAV, "JUBIAR": ""}, **cambios}
    s.guardar_parametros(datos, "admin")


def configurado(s):
    parametros(s)
    s.cargar_certificado(firmar_csr(s.generar_pedido("admin")), "admin")


def alta(s, **cambios):
    datos = {"empresa": "ENAV", "cuit_emisor": PROVEEDOR, "razon_social": "Proveedor SA", "tipo_comprobante": 1,
             "punto_venta": 1, "numero": 1, "fecha": date(2026, 11, 10), "importe_total": 121000.5,
             "autorizacion": "CAE", "codigo_autorizacion": CAE, **cambios}
    return s.crear_factura(datos, "administracion")


def estados(factura):
    return {int(r.control): r.estado.value for r in factura.resultados}


# --- Dominio ----------------------------------------------------------------

def test_cuit_con_digito_verificador():
    assert cuit_valido(PROVEEDOR) and cuit_valido(REPRESENTANTE)
    assert not cuit_valido("30693135670") and not cuit_valido("3069313567") and not cuit_valido("3069313567a")


def test_nombres_de_pdf_como_los_pide_administracion():
    assert nombre_pdf("30693135679", 1, date(2017, 9, 26)) == "30693135679_1_26-09-2017"
    assert nombre_pdf("30693135679", 4, date(2017, 9, 26), 1) == "30693135679_4_00000001_26-09-2017"
    assert nombre_pdf("30693135679", 3, date(2017, 9, 26), 1) == "30693135679_3_26-09-2017"
    with pytest.raises(ValueError):
        nombre_pdf("30693135679", 4, date(2017, 9, 26))


def test_reglas_de_cada_control():
    apocrifas = Padron("apocrifas", "u", datetime.now(UTC), "", {APOCRIFO: (("08/11/2005", "08/11/2005", ""),)})
    assert evaluar_apocrifa(apocrifas, APOCRIFO)[0] is Estado.ALERTA
    assert evaluar_apocrifa(apocrifas, PROVEEDOR)[0] is Estado.OK
    rg18 = Padron("rg18", "u", datetime.now(UTC), "", {AGENTE: (("A", "01/11/2019", "31/12/2020", "B"),)})
    assert "no a la fecha" in evaluar_rg18(rg18, AGENTE, date(2026, 1, 1))[1]
    assert "Es agente" in evaluar_rg18(rg18, AGENTE, date(2020, 1, 1))[1]
    assert evaluar_constancia(Constancia(False))[0] is Estado.ALERTA
    assert evaluar_constancia(Constancia(True, "X", "INACTIVO", ("IVA",)))[0] is Estado.ALERTA
    assert evaluar_constancia(Constancia(True, "X", "ACTIVO", (), "", ("No posee impuestos",)))[0] is Estado.ALERTA
    assert evaluar_constancia(Constancia(True, "X", "ACTIVO", (), "Categoría A"))[0] is Estado.OK
    assert evaluar_constatacion(Constatacion("A"), "CAE")[0] is Estado.OK
    assert evaluar_constatacion(Constatacion("R", ("No existe (código 1)",)), "CAE")[0] is Estado.ALERTA


def test_validaciones_de_la_factura():
    s = servicio()
    for cambio, texto in [({"cuit_emisor": "30693135670"}, "CUIT"), ({"importe_total": float("nan")}, "importe"),
                          ({"importe_total": float("inf")}, "importe"), ({"importe_total": -1}, "importe"),
                          ({"codigo_autorizacion": "123"}, "14 números"), ({"tipo_comprobante": 99}, "tipo"),
                          ({"fecha": date(2026, 12, 1)}, "posterior"), ({"empresa": "OTRA"}, "empresa"),
                          ({"autorizacion": "CF", "codigo_autorizacion": CAE}, "controlador")]:
        with pytest.raises(ValueError, match=texto):
            alta(s, **cambio)
    alta(s)
    with pytest.raises(ValueError, match="ya está cargada"):
        alta(s)
    assert alta(s, empresa="JUBIAR").empresa == "JUBIAR"


# --- Flujo con fakes ---------------------------------------------------------

def test_sin_certificado_inscripcion_y_comprobante_quedan_sin_configurar():
    conector = Conector()
    s = servicio(conector)
    factura = s.correr(alta(s).id, "administracion")
    assert estados(factura) == {1: "pendiente", 2: "sin_configurar", 3: "ok", 4: "sin_configurar", 5: "ok"}
    assert conector.llamadas == []
    assert not factura.alerta


def test_corre_los_controles_y_guarda_cada_pdf_con_su_nombre():
    conector = Conector()
    s = servicio(conector)
    configurado(s)
    factura = s.correr(alta(s).id, "administracion")
    assert estados(factura) == {1: "pendiente", 2: "ok", 3: "ok", 4: "ok", 5: "ok"}
    # Se consulta con el CUIT del certificado; la empresa va como receptora de la factura.
    assert conector.llamadas == [("constancia", "homologacion", REPRESENTANTE, PROVEEDOR, True),
                                 ("constatar", "homologacion", REPRESENTANTE, 1, True)]
    assert conector.receptor == ENAV
    nombre, pdf = s.archivo(factura.id, 4)
    assert nombre == "30693135679_4_00000001_18-11-2026.pdf" and pdf.startswith(b"%PDF-")
    assert s.archivo(factura.id, 2)[0] == "30693135679_2_18-11-2026.pdf"
    with pytest.raises(LookupError):
        s.archivo(factura.id, 1)
    vista = s.vista(factura)
    assert vista["controles"][0]["puede_subir"] is True and vista["controles"][1]["puede_subir"] is False


def test_un_control_mal_marca_la_factura_en_alerta():
    s = servicio(Conector(constatacion=Constatacion("R", ("El CAE no corresponde (código 102)",))))
    configurado(s)
    factura = s.correr(alta(s, cuit_emisor=APOCRIFO).id, "administracion")
    assert estados(factura)[3] == "alerta" and estados(factura)[4] == "alerta"
    assert factura.alerta and s.listar(solo_alertas=True)[0]["id"] == factura.id
    assert "CAE no corresponde" in factura.resultado(4).detalle


def test_controlador_fiscal_no_se_controla_segun_parametros():
    conector = Conector()
    s = servicio(conector)
    configurado(s)
    factura = s.correr(alta(s, autorizacion="CF", codigo_autorizacion="", tipo_comprobante=81).id, "admin")
    assert estados(factura)[4] == "no_aplica" and "controlador fiscal" in factura.resultado(4).detalle
    assert [ll[0] for ll in conector.llamadas] == ["constancia"]
    # Si cambia la normativa: se apaga la excepción y queda pendiente de control a mano.
    parametros(s, excluir_controlador_fiscal=False)
    factura = s.correr(factura.id, "admin")
    assert estados(factura)[4] == "pendiente"
    pdf = b"%PDF-1.4 constancia"
    factura = s.subir_constancia(factura.id, 4, pdf, "ok", "", "admin")
    assert estados(factura)[4] == "ok" and s.archivo(factura.id, 4) == ("30693135679_4_00000001_18-11-2026.pdf", pdf)


def test_controles_apagados_en_parametros_no_aplican():
    s = servicio(Conector())
    configurado(s)
    parametros(s, controles_activos=[2, 3])
    factura = s.correr(alta(s).id, "admin")
    assert estados(factura) == {1: "no_aplica", 2: "ok", 3: "ok", 4: "no_aplica", 5: "no_aplica"}


def test_si_arca_no_responde_queda_para_reintentar():
    s = servicio(Conector(falla=ErrorARCA("No hubo conexión con ARCA.")))
    configurado(s)
    factura = s.correr(alta(s).id, "admin")
    assert estados(factura)[2] == "error" and factura.resultado(2).detalle == "No hubo conexión con ARCA."
    s2 = servicio(Conector(falla=OSError("10.0.0.1 caído")))
    configurado(s2)
    factura = s2.correr(alta(s2).id, "admin")
    assert "10.0.0.1" not in factura.resultado(4).detalle and estados(factura)[4] == "error"


def test_control_impositivo_manual_y_reuso_en_el_dia():
    s = servicio()
    primera = s.correr(alta(s).id, "admin")
    with pytest.raises(ValueError, match="PDF"):
        s.subir_constancia(primera.id, 1, b"no es pdf", "ok", "", "admin")
    with pytest.raises(ValueError, match="encontraste"):
        s.subir_constancia(primera.id, 1, b"%PDF-1.4", "alerta", "", "admin")
    with pytest.raises(ValueError, match="no se reemplaza"):
        s.subir_constancia(primera.id, 3, b"%PDF-1.4", "ok", "", "admin")
    primera = s.subir_constancia(primera.id, 1, b"%PDF-1.4 reproweb", "ok", "Sin observaciones", "admin")
    assert s.archivo(primera.id, 1)[0] == "30693135679_1_18-11-2026.pdf"
    assert estados(s.correr(primera.id, "admin"))[1] == "ok"  # volver a correr no la borra
    segunda = s.correr(alta(s, numero=2).id, "admin")
    assert estados(segunda)[1] == "ok" and s.archivo(segunda.id, 1)[1] == b"%PDF-1.4 reproweb"


def test_listados_se_bajan_una_vez_y_se_actualizan_vencidos():
    reloj, descargas = Reloj(), Descargas()
    s = servicio(reloj=reloj, descargas=descargas)
    s.correr(alta(s).id, "admin")
    s.correr(alta(s, numero=2).id, "admin")
    assert descargas.bajadas == ["apocrifas", "rg18"]
    assert s.actualizar_vencidos() == []
    reloj.ahora += timedelta(hours=25)
    assert s.actualizar_vencidos() == ["apocrifas", "rg18"]


# --- Certificado ---------------------------------------------------------------

def test_certificado_se_genera_en_el_servidor_y_la_clave_no_sale():
    s = servicio()
    csr = s.generar_pedido("admin")
    pedido = x509.load_pem_x509_csr(csr.encode())
    assert pedido.is_signature_valid and pedido.public_key().key_size == 2048
    assert pedido.subject.get_attributes_for_oid(NameOID.SERIAL_NUMBER)[0].value == f"CUIT {REPRESENTANTE}"
    guardada = s.repo.credenciales["pendiente:homologacion"]
    assert b"PRIVATE KEY" not in guardada.clave_cifrada
    assert "PRIVATE KEY" not in str(s.estado_certificado())
    with pytest.raises(ValueError, match="no corresponde"):
        s.cargar_certificado(firmar_csr(servicio().generar_pedido("x")), "admin")
    with pytest.raises(ValueError, match="CUIT"):
        s.cargar_certificado(firmar_csr(csr, cuit="20111111112"), "admin")
    with pytest.raises(ValueError, match="clave privada"):
        s.cargar_certificado("-----BEGIN PRIVATE KEY-----\n-----BEGIN CERTIFICATE-----", "admin")
    estado = s.cargar_certificado(firmar_csr(csr), "admin")
    assert estado["activo"]["cuit"] == REPRESENTANTE and estado["pedido"] is None
    # Otro ambiente, otro certificado.
    parametros(s, ambiente="produccion")
    assert s.estado_certificado()["activo"] is None


# --- Clientes de ARCA con transporte falso -------------------------------------

def test_wsaa_firma_el_tra_y_guarda_el_permiso_hasta_que_vence():
    certificados = CertificadosRSA()
    clave, csr = certificados.generar_pedido(REPRESENTANTE, "suitejuviarhomo", "Suite Juviar")
    certificado = firmar_csr(csr)
    reloj = Reloj()
    pedidos = []
    vence = (reloj.ahora + timedelta(hours=12)).isoformat()

    def responder(pedido: httpx.Request) -> httpx.Response:
        cuerpo = pedido.content.decode()
        pedidos.append((str(pedido.url), cuerpo))
        if "loginCms" in cuerpo:
            cms = base64.b64decode(cuerpo.split("<wsaa:in0>")[1].split("</wsaa:in0>")[0])
            firmados = pkcs7.load_der_pkcs7_certificates(cms)
            assert firmados[0].subject.rfc4514_string().startswith(f"2.5.4.5=CUIT {REPRESENTANTE}")
            ticket = (f"&lt;loginTicketResponse&gt;&lt;header&gt;&lt;expirationTime&gt;{vence}&lt;/expirationTime&gt;"
                      "&lt;/header&gt;&lt;credentials&gt;&lt;token&gt;TOK&lt;/token&gt;&lt;sign&gt;SIG&lt;/sign&gt;"
                      "&lt;/credentials&gt;&lt;/loginTicketResponse&gt;")
            return httpx.Response(200, text=f"<Envelope><Body><loginCmsResponse><loginCmsReturn>{ticket}"
                                            "</loginCmsReturn></loginCmsResponse></Body></Envelope>")
        if "getPersona_v2" in cuerpo:
            assert "<token>TOK</token>" in cuerpo and f"<cuitRepresentada>{REPRESENTANTE}</cuitRepresentada>" in cuerpo
            return httpx.Response(200, text=(
                "<Envelope><Body><getPersona_v2Response><personaReturn><datosGenerales><estadoClave>ACTIVO"
                "</estadoClave><razonSocial>PROVEEDOR SA</razonSocial></datosGenerales><datosRegimenGeneral>"
                "<impuesto><descripcionImpuesto>IVA</descripcionImpuesto></impuesto></datosRegimenGeneral>"
                "</personaReturn></getPersona_v2Response></Body></Envelope>"))
        assert pedido.headers["SOAPAction"] == '"http://servicios1.afip.gob.ar/wscdc/ComprobanteConstatar"'
        assert "<CbteModo>CAE</CbteModo>" in cuerpo and "<CbteFch>20261110</CbteFch>" in cuerpo
        assert f"<Cuit>{REPRESENTANTE}</Cuit>" in cuerpo and f"<DocNroReceptor>{ENAV}</DocNroReceptor>" in cuerpo
        return httpx.Response(200, text=(
            "<Envelope><Body><ComprobanteConstatarResponse><ComprobanteConstatarResult><Resultado>A</Resultado>"
            "</ComprobanteConstatarResult></ComprobanteConstatarResponse></Body></Envelope>"))

    tickets = {}
    conector = ConectorARCAWeb(tickets, CifradorARCA.desde_secreto("x"),
                               httpx.Client(transport=httpx.MockTransport(responder)), reloj)
    acceso = AccesoARCA("homologacion", certificado, clave)
    s = servicio()
    factura = alta(s)
    assert conector.constancia(acceso, REPRESENTANTE, PROVEEDOR).razon_social == "PROVEEDOR SA"
    assert conector.constancia(acceso, REPRESENTANTE, PROVEEDOR).impuestos == ("IVA",)
    assert conector.constatar(acceso, REPRESENTANTE, factura, ENAV).resultado == "A"
    logins = [u for u, _ in pedidos if "wsaahomo" in u]
    assert len(logins) == 2  # uno por servicio; la segunda constancia reusó el permiso
    assert all(b"TOK" not in v for v in tickets.values())  # guardado cifrado
    reloj.ahora += timedelta(hours=12)
    conector.constancia(acceso, REPRESENTANTE, PROVEEDOR)
    assert len([u for u, _ in pedidos if "wsaahomo" in u]) == 3


def test_tra_y_firma_cms():
    tra = armar_tra("wscdc", datetime(2026, 11, 18, 13, tzinfo=UTC))
    assert "<service>wscdc</service>" in tra and "2026-11-18T09:50:00-03:00" in tra
    clave, csr = CertificadosRSA().generar_pedido(REPRESENTANTE, "a", "b")
    firmado = base64.b64decode(firmar_tra(tra, firmar_csr(csr), clave))
    assert tra.encode() in firmado  # el TRA va adentro del CMS (no separado)


def test_lectura_de_respuestas_de_arca():
    assert leer_constancia(b"<Envelope><Body><Fault><faultstring>No existe persona con ese Id</faultstring>"
                           b"</Fault></Body></Envelope>").encontrada is False
    con_error = leer_constancia(b"<E><personaReturn><datosGenerales><estadoClave>ACTIVO</estadoClave>"
                                b"</datosGenerales><errorConstancia><error>No posee impuestos activos</error>"
                                b"</errorConstancia></personaReturn></E>")
    assert con_error.errores == ("No posee impuestos activos",)
    rechazo = leer_constatacion(b"<E><ComprobanteConstatarResult><Resultado>R</Resultado><Observaciones><Obs>"
                                b"<Code>102</Code><Msg>No existe</Msg></Obs></Observaciones>"
                                b"</ComprobanteConstatarResult></E>")
    assert rechazo == Constatacion("R", ("No existe (código 102)",))
    with pytest.raises(ErrorARCA):
        leer_constatacion(b"<E><ComprobanteConstatarResult><Errors><Err><Code>600</Code><Msg>Token</Msg></Err>"
                          b"</Errors></ComprobanteConstatarResult></E>")
    with pytest.raises(ErrorARCA):
        leer_constancia(b'<!DOCTYPE x [<!ENTITY a "b">]><E>&a;</E>')


def test_lectura_de_los_listados_completos():
    txt = ("# AFIP - Facturas Apocrifas\t\r\n# Generado - 18/11/2026\t\r\n# Estructura del Archivo: CUIT\t\r\n"
           "30703948983,08/11/2005,08/11/2005,,\t\r\n24060509693,28/04/2004,28/04/2004,,\t\r\n").encode("latin-1")
    zipeado = io.BytesIO()
    with zipfile.ZipFile(zipeado, "w") as z:
        z.writestr("FacturasApocrifas.txt", txt)
    generado, registros = leer_apocrifas(zipeado.getvalue())
    assert generado == "18/11/2026" and registros[APOCRIFO] == (("08/11/2005", "08/11/2005", ""),)
    csv = ("RG 18 - Agentes de Retención    17/11/2026 02:11   \r\nCUIT;RAZON SOCIAL;FECHA_DESDE;FECHA_HASTA;INCISO_RG\r\n"
           "34605699075;HAWLEY SA;01/12/2001;30/06/2010;D  \r\n34605699075;HAWLEY SA;01/09/1999;30/09/1999;C\r\n"
           ).encode("latin-1")
    generado, registros = leer_rg18(csv)
    assert generado == "17/11/2026 02:11" and len(registros["34605699075"]) == 2


# --- API y permisos -----------------------------------------------------------

def cliente(perfil, s):
    app = FastAPI()
    app.include_router(crear_router(s, "prueba"), prefix="/controles-arca")
    return TestClient(app, headers={"X-Perfil-Simulado": perfil, "X-Actor-Simulado": perfil.lower()})


ALTA = {"empresa": "ENAV", "cuit_emisor": PROVEEDOR, "tipo_comprobante": 1, "punto_venta": 1, "numero": 7,
        "fecha": "2026-11-10", "importe_total": 1500, "autorizacion": "CAE", "codigo_autorizacion": CAE}


def test_permisos_por_perfil():
    assert PERMISOS_POR_PERFIL["ADMINISTRACION"] == {"suite.acceder", "controles_fiscales.operar"}
    assert "controles_fiscales.operar" in PERMISOS_POR_PERFIL["COMPRAS"]
    assert "controles_fiscales.operar" in PERMISOS_POR_PERFIL["SUPERADMIN"]
    s = servicio(Conector())
    assert cliente("RRHH", s).get("/controles-arca/facturas").status_code == 403
    assert cliente("COMERCIAL", s).post("/controles-arca/facturas", json=ALTA).status_code == 403
    nueva = cliente("ADMINISTRACION", s).post("/controles-arca/facturas", json=ALTA)
    assert nueva.status_code == 201, nueva.text
    corrida = cliente("COMPRAS", s).post(f"/controles-arca/facturas/{nueva.json()['id']}/controles")
    assert corrida.status_code == 200 and corrida.json()["controles"][0]["estado"] == "pendiente"
    assert cliente("ADMINISTRACION", s).get("/controles-arca/parametros").status_code == 403
    assert cliente("ADMINISTRACION", s).post("/controles-arca/certificado/pedido").status_code == 403
    assert cliente("SUPERADMIN", s).get("/controles-arca/parametros").json()["cuit_representante"] == REPRESENTANTE


def test_validacion_de_entradas_de_la_api():
    c = cliente("ADMINISTRACION", servicio())
    for cambio in ({"importe_total": "NaN"}, {"importe_total": "Infinity"}, {"importe_total": -5},
                   {"importe_total": 0}, {"numero": 0}, {"punto_venta": 100000}, {"autorizacion": "OTRA"},
                   {"empresa": "ACME"}, {"fecha": "18/11/2026"}):
        assert c.post("/controles-arca/facturas", json={**ALTA, **cambio}).status_code == 422, cambio
    assert c.post("/controles-arca/facturas", json={**ALTA, "cuit_emisor": "30693135670"}).status_code == 400
    fid = c.post("/controles-arca/facturas", json=ALTA).json()["id"]
    c.post(f"/controles-arca/facturas/{fid}/controles")
    ruta = f"/controles-arca/facturas/{fid}/controles/1/constancia"
    assert c.post(ruta, json={"contenido_base64": "%%%", "resultado": "ok"}).status_code == 400
    assert c.post(ruta, json={"contenido_base64": "QUJD", "resultado": "ok"}).status_code == 400
    assert c.post(ruta, json={"contenido_base64": "QUJD", "resultado": "quizas"}).status_code == 422
    assert c.post(f"/controles-arca/facturas/{fid}/controles/9/constancia",
                  json={"contenido_base64": "QUJD", "resultado": "ok"}).status_code == 422
    pdf = base64.b64encode(b"%PDF-1.4 reproweb").decode()
    assert c.post(ruta, json={"contenido_base64": pdf, "resultado": "ok"}).status_code == 200
    bajada = c.get(f"/controles-arca/facturas/{fid}/controles/1/pdf")
    assert bajada.content == b"%PDF-1.4 reproweb"
    assert 'filename="30693135679_1_' in bajada.headers["content-disposition"]


def test_la_api_nunca_devuelve_la_clave_privada():
    s = servicio()
    admin = cliente("SUPERADMIN", s)
    respuestas = [admin.post("/controles-arca/certificado/pedido")]
    assert respuestas[0].status_code == 200
    csr = respuestas[0].json()["csr_pem"]
    assert "CERTIFICATE REQUEST" in csr
    respuestas.append(admin.get("/controles-arca/certificado/pedido"))
    assert respuestas[-1].text == csr
    respuestas.append(admin.put("/controles-arca/certificado", json={"certificado_pem": firmar_csr(csr)}))
    assert respuestas[-1].status_code == 200 and respuestas[-1].json()["activo"]["cuit"] == REPRESENTANTE
    respuestas += [admin.get("/controles-arca/certificado"), admin.get("/controles-arca/parametros"),
                   admin.get("/controles-arca/catalogo")]
    for r in respuestas:
        assert "PRIVATE KEY" not in r.text and "clave_cifrada" not in r.text
    assert admin.get("/controles-arca/catalogo").json()["faltantes"] == [
        "Falta cargar en Parámetros el CUIT de ENAV.", "Falta cargar en Parámetros el CUIT de JUBIAR."]


def test_el_cifrado_viejo_solo_se_usa_con_el_servidor_que_lo_necesita():
    from suite_juviar.modulos.controles_arca.infrastructure.arca import HOSTS_CIFRADO_VIEJO
    assert HOSTS_CIFRADO_VIEJO == {"servicios1.afip.gov.ar"}


def test_parametros_validan_cuits_y_urls():
    s = servicio()
    with pytest.raises(ValueError, match="ENAV"):
        parametros(s, cuit_empresas={"ENAV": "30546689970", "JUBIAR": ""})
    with pytest.raises(ValueError, match="sitio de ARCA"):
        parametros(s, url_apocrifas="https://ejemplo.com/lista.zip")
    with pytest.raises(ValueError, match="sitio de ARCA"):
        parametros(s, url_rg18="http://servicioscf.afip.gob.ar/Publico/rg18/Archivos/RG18.csv")
    # Direcciones armadas para engañar una comparación de texto.
    for engano in ("https://servicioscf.afip.gob.ar@127.0.0.1/x", "https://127.0.0.1#.afip.gob.ar/x",
                   "https://servicioscf.afip.gob.ar:8080/x", "https://evil.com\\@servicioscf.afip.gob.ar/x",
                   "https://usuario:clave@servicioscf.afip.gob.ar/x", "https://servicioscf.afip.gob.ar/x\ty",
                   "https://servicioscf.afip.gob.ar\n.evil.com/x", "https://servicioscf.afіp.gob.ar/x"):
        with pytest.raises(ValueError, match="sitio de ARCA"):
            parametros(s, url_rg18=engano)
    c = cliente("SUPERADMIN", s)
    datos = {**s.vista_parametros(), "controles_activos": [1, 6]}
    datos.pop("actualizado_por"), datos.pop("actualizado_en")
    assert c.put("/controles-arca/parametros", json=datos).status_code == 422
    datos["controles_activos"] = [1, 2]
    assert c.put("/controles-arca/parametros", json=datos).json()["controles_activos"] == [1, 2]
