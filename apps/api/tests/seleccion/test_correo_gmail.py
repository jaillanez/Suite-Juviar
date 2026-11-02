import imaplib
import tempfile
from datetime import UTC, date, datetime
from email.message import EmailMessage
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from suite_juviar.modulos.seleccion.api.app import construir_correo, crear_router_parametros
from suite_juviar.modulos.seleccion.application.correo import CorreoRRHH
from suite_juviar.modulos.seleccion.infrastructure.correo_gmail import BandejaGmailIMAP, ErrorCorreo
from suite_juviar.modulos.seleccion.infrastructure.lectura_nocturna import segundos_hasta
from suite_juviar.modulos.seleccion.infrastructure.sqlite import OriginalesSQLite, correo_rrhh_sqlite

CLAVE = "abcd efgh ijkl mnop"


def correo_con(*adjuntos: tuple[str, bytes], message_id: str = "<cv-1@gmail.com>") -> bytes:
    mensaje = EmailMessage()
    mensaje["From"] = "postulante@example.com"
    mensaje["To"] = "rrhh@gmail.com"
    mensaje["Subject"] = "CV"
    mensaje["Date"] = "Mon, 02 Nov 2026 10:00:00 -0300"
    mensaje["Message-ID"] = message_id
    mensaje.set_content("Adjunto mi CV")
    for nombre, contenido in adjuntos:
        mensaje.add_attachment(contenido, maintype="application", subtype="octet-stream", filename=nombre)
    return mensaje.as_bytes()


class GmailFalso:
    def __init__(self, correos: list[bytes], clave_valida: str = CLAVE.replace(" ", "")) -> None:
        self.correos = correos
        self.clave_valida = clave_valida
        self.solo_lectura = None
        self.pedidos: list[str] = []

    def __call__(self, servidor: str):
        assert servidor == "imap.gmail.com"
        return self

    def login(self, usuario, clave):
        if clave != self.clave_valida:
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")

    def select(self, bandeja, readonly=False):
        self.solo_lectura = readonly
        return "OK", [b"1"]

    def search(self, charset, criterio):
        self.pedidos.append(criterio)
        return "OK", [b" ".join(str(i + 1).encode() for i in range(len(self.correos)))]

    def fetch(self, numero, partes):
        self.pedidos.append(partes)
        crudo = self.correos[int(numero) - 1]
        if partes == "(RFC822.SIZE)":
            return "OK", [f"{int(numero)} (RFC822.SIZE {len(crudo)})".encode()]
        return "OK", [(b"1 (BODY[] {1}", crudo), b")"]

    def logout(self):
        return "BYE", []


def test_trae_solo_adjuntos_de_cv_sin_marcar_correos_como_leidos():
    gmail = GmailFalso([correo_con(("cv.pdf", b"%PDF-1.4 cv"), ("foto.JPG", b"jpg"), ("carta.docx", b"doc"))])
    documentos = BandejaGmailIMAP("RRHH@gmail.com", CLAVE, date(2026, 10, 1), gmail).listar_nuevos()

    assert [d.nombre_archivo for d in documentos] == ["cv.pdf", "foto.JPG"]
    assert documentos[0].referencia_fuente == "gmail:rrhh@gmail.com:<cv-1@gmail.com>:cv.pdf"
    assert documentos[0].fuente_simulada is False
    assert gmail.solo_lectura is True
    assert "(SINCE 01-Oct-2026)" in gmail.pedidos
    assert "(BODY.PEEK[])" in gmail.pedidos


def test_clave_rechazada_explica_que_debe_ser_de_aplicacion():
    with pytest.raises(ErrorCorreo, match="contraseña de aplicación"):
        BandejaGmailIMAP("rrhh@gmail.com", "otra", date(2026, 10, 1), GmailFalso([])).probar()


def servicio(gmail: GmailFalso) -> tuple[CorreoRRHH, str]:
    ruta = str(Path(tempfile.mkdtemp()) / "modulos.sqlite3")
    correo = construir_correo(ruta, "clave-de-prueba")
    correo._crear_bandeja = lambda casilla, clave, ultima: BandejaGmailIMAP(casilla, clave, date(2026, 10, 1), gmail)
    return correo, ruta


def test_la_clave_se_guarda_cifrada_y_nunca_se_devuelve():
    correo, ruta = servicio(GmailFalso([]))
    with pytest.raises(ValueError, match="contraseña de aplicación"):
        correo.guardar("ENAV", "rrhh@gmail.com", None, "admin")

    vista = correo.guardar("enav", "rrhh@gmail.com", CLAVE, "admin")

    assert vista["clave_cargada"] is True
    assert "clave" not in vista
    guardado = correo_rrhh_sqlite(ruta)["ENAV"]["clave"]
    assert CLAVE.replace(" ", "").encode() not in guardado
    # Cambiar sólo la casilla conserva la clave ya cargada.
    assert correo.guardar("ENAV", "otra@gmail.com", "", "admin")["clave_cargada"] is True


def test_empresas_separadas_y_casilla_invalida():
    correo, _ = servicio(GmailFalso([]))
    correo.guardar("JUBIAR", "jubiar@gmail.com", CLAVE, "admin")
    assert correo.ver("ENAV")["clave_cargada"] is False
    with pytest.raises(ValueError):
        correo.guardar("OTRA", "x@gmail.com", CLAVE, "admin")
    with pytest.raises(ValueError, match="no es válida"):
        correo.guardar("ENAV", "sin-arroba", CLAVE, "admin")


def test_leer_dos_veces_no_duplica_y_reenvio_del_mismo_cv_tampoco():
    pdf = b"%PDF-1.4 mismo cv"
    gmail = GmailFalso([correo_con(("cv.pdf", pdf))])
    correo, ruta = servicio(gmail)
    correo.guardar("ENAV", "rrhh@gmail.com", CLAVE, "admin")

    primera = correo.leer("ENAV")
    assert (primera.adjuntos, primera.incorporados) == (1, 1)

    gmail.correos.append(correo_con(("cv-de-nuevo.pdf", pdf), message_id="<cv-2@gmail.com>"))
    segunda = correo.leer("ENAV")

    assert (segunda.adjuntos, segunda.incorporados, segunda.repetidos) == (2, 0, 2)
    assert len(OriginalesSQLite(ruta).listar_originales()) == 1
    assert correo.ver("ENAV")["ultimo_resultado"]["incorporados"] == 0


def test_un_error_de_gmail_no_avanza_la_ultima_lectura():
    gmail = GmailFalso([])
    correo, _ = servicio(gmail)
    correo.guardar("ENAV", "rrhh@gmail.com", CLAVE, "admin")
    gmail.clave_valida = "cambiada"

    with pytest.raises(ErrorCorreo):
        correo.leer("ENAV")

    vista = correo.ver("ENAV")
    assert vista["ultima_lectura"] is None
    assert "rechazó" in vista["ultimo_resultado"]["error"]
    assert correo.leer_todas()[0].error


def cliente(perfil: str) -> TestClient:
    correo, _ = servicio(GmailFalso([]))
    app = FastAPI()
    app.include_router(crear_router_parametros(correo), prefix="/parametros")
    return TestClient(app, headers={"X-Perfil-Simulado": perfil})


def test_solo_administradores_ven_y_cambian_parametros():
    assert cliente("RRHH").get("/parametros/correo-rrhh").status_code == 403
    assert cliente("RRHH").put("/parametros/correo-rrhh/ENAV", json={"casilla": "a@gmail.com"}).status_code == 403

    admin = cliente("SUPERADMIN")
    respuesta = admin.put("/parametros/correo-rrhh/ENAV",
                          json={"casilla": "rrhh@gmail.com", "clave_aplicacion": CLAVE})
    assert respuesta.status_code == 200
    assert CLAVE not in respuesta.text
    assert [f["empresa"] for f in admin.get("/parametros/correo-rrhh").json()] == ["ENAV", "JUBIAR"]
    assert admin.post("/parametros/correo-rrhh/ENAV/probar").json() == {"ok": True}
    assert admin.post("/parametros/correo-rrhh/JUBIAR/probar").status_code == 400


def test_sin_clave_de_parametros_en_produccion_avisa():
    app = FastAPI()
    app.include_router(crear_router_parametros(None), prefix="/parametros")
    respuesta = TestClient(app, headers={"X-Perfil-Simulado": "SUPERADMIN"}).get("/parametros/correo-rrhh")
    assert respuesta.status_code == 503


def test_lectura_nocturna_espera_hasta_la_hora_pedida():
    ahora = datetime(2026, 11, 2, 1, 30, tzinfo=UTC)
    assert segundos_hasta(2, ahora) == 30 * 60
    assert segundos_hasta(1, ahora) == 23.5 * 3600


def test_un_correo_mal_armado_no_frena_al_resto():
    roto = correo_con(("cv.pdf", b"%PDF roto"), message_id="<roto@gmail.com>").replace(
        b'filename="cv.pdf"', b'filename="=?utf-8?b?###?="')
    gmail = GmailFalso([roto, correo_con(("bueno.pdf", b"%PDF-1.4 ok"), message_id="<ok@gmail.com>")])
    documentos = BandejaGmailIMAP("rrhh@gmail.com", CLAVE, date(2026, 10, 1), gmail).listar_nuevos()
    assert "bueno.pdf" in [d.nombre_archivo for d in documentos]


def test_correos_demasiado_grandes_no_se_descargan(monkeypatch):
    from suite_juviar.modulos.seleccion.infrastructure import correo_gmail
    monkeypatch.setattr(correo_gmail, "TAMANO_MAXIMO_CORREO", 10)
    gmail = GmailFalso([correo_con(("cv.pdf", b"%PDF-1.4 cv"))])
    assert BandejaGmailIMAP("rrhh@gmail.com", CLAVE, date(2026, 10, 1), gmail).listar_nuevos() == []
    assert "(BODY.PEEK[])" not in gmail.pedidos
