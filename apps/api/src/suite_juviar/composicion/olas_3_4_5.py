"""Único lugar que conecta los puertos de las olas nuevas con adaptadores."""

from __future__ import annotations

import os
from pathlib import Path

from suite_juviar.modulos.activos.api.app import crear_router as crear_activos
from suite_juviar.modulos.activos.infrastructure.guardia_dmz import PuertaDMZ
from suite_juviar.modulos.capacitacion.api.app import crear_router as crear_capacitacion
from suite_juviar.modulos.capacitacion.infrastructure.configuracion_yaml import (
    ConfiguracionCapacitacionYAML,
)
from suite_juviar.modulos.controles_arca.api.app import crear_router as crear_controles_arca
from suite_juviar.modulos.controles_arca.application.servicios import GestionarControles
from suite_juviar.modulos.controles_arca.infrastructure import padrones as padrones_arca
from suite_juviar.modulos.controles_arca.infrastructure.arca import ConectorARCAWeb
from suite_juviar.modulos.controles_arca.infrastructure.certificados import CertificadosRSA
from suite_juviar.modulos.controles_arca.infrastructure.cifrado import CifradorARCA
from suite_juviar.modulos.controles_arca.infrastructure.lector import LectorFacturasLocal
from suite_juviar.modulos.controles_arca.infrastructure.pdf import ConstanciaPDF
from suite_juviar.modulos.controles_arca.infrastructure.qr import LectorQRServidor
from suite_juviar.modulos.controles_arca.infrastructure.sqlite import ControlesSQLite
from suite_juviar.modulos.epp_analitica.api.app import crear_router as crear_analitica
from suite_juviar.modulos.epp_analitica.application.servicios import AnalizarEPP
from suite_juviar.modulos.epp_analitica.infrastructure.simulados import (
    FuenteEntregasDesdePuerto,
    NombresDesdePuerto,
    PreciosSimulados,
)
from suite_juviar.modulos.legajo.api.app import crear_router as crear_legajo
from suite_juviar.modulos.legajo.application.servicios import GestionarLegajo
from suite_juviar.modulos.legajo.infrastructure.simulados import (
    FuenteLegajosDesdePuerto,
)
from suite_juviar.modulos.legajo.infrastructure.sqlite import AdjuntosCifradosSQLite
from suite_juviar.modulos.mosto.api.app import crear_router as crear_mosto
from suite_juviar.modulos.mosto.application.servicios import GestionarMosto
from suite_juviar.modulos.mosto.infrastructure import avisos as avisos_mosto
from suite_juviar.modulos.mosto.infrastructure.sqlite import MostoSQLite
from suite_juviar.modulos.rrhh_whatsapp.api.app import crear_router as crear_rrhh_whatsapp
from suite_juviar.modulos.rrhh_whatsapp.application.servicios import BandejaRRHH
from suite_juviar.modulos.rrhh_whatsapp.infrastructure.dmz import PuertaDMZ as PuertaRRHHDMZ
from suite_juviar.modulos.rrhh_whatsapp.infrastructure.dmz import (
    PuertaSinConfigurar as PuertaRRHHSinConfigurar,
)
from suite_juviar.modulos.rrhh_whatsapp.infrastructure.sqlite import BandejaCifradaSQLite
from suite_juviar.modulos.salud.api.app import crear_router as crear_salud
from suite_juviar.modulos.salud.application.lector_certificados import (
    analizar_certificado,
    usaria_ia_externa,
)
from suite_juviar.modulos.salud.application.servicios import GestionarSalud
from suite_juviar.modulos.salud.infrastructure.simulados import (
    FuenteLaboralSimulada,
)
from suite_juviar.modulos.salud.infrastructure.sqlite import (
    AdjuntosSaludCifradosSQLite,
    CatalogoDiagnosticoSQLite,
    SaludSQLite,
)
from suite_juviar.modulos.seleccion.api.app import (
    construir_correo,
    construir_cvs_whatsapp,
    crear_router_parametros,
)
from suite_juviar.modulos.seleccion.api.app import crear_router as crear_seleccion
from suite_juviar.modulos.seleccion.infrastructure import lectura_nocturna
from suite_juviar.modulos.seleccion.infrastructure.perfiles_yaml import CriteriosPerfilYAML
from suite_juviar.modulos.turnos.api.app import crear_router as crear_turnos
from suite_juviar.modulos.turnos.application.servicios import ConciliarTurnos
from suite_juviar.modulos.turnos.infrastructure.sqlite import (
    EstadoTurnosSQLite,
    ExportadorArchivoLocal,
    FuenteFichadasSQLite,
)
from suite_juviar.plataforma.identidad.api.dependencias import configurar_envio_correo
from suite_juviar.plataforma.terceros.api.personal_bot import configurar as configurar_personal_bot
from suite_juviar.plataforma.terceros.api.tablero_fila import NOMBRES as NOMBRES_SEDES
from suite_juviar.plataforma.terceros.api.tablero_fila import sedes as sedes_fila


def construir_routers(rrhh):
    entorno = (os.getenv("SJ_ENTORNO") or os.getenv("ENTORNO") or "desarrollo").lower()
    clave_adjuntos = os.getenv("SJ_LEGAJO_CLAVE_PRUEBA", "0" * 32).encode()
    ruta_modulos = os.getenv("SJ_MODULOS_SQLITE_PATH") or str(
        Path(__file__).parents[3] / "datos" / "modulos.sqlite3"
    )
    analitica = AnalizarEPP(
        FuenteEntregasDesdePuerto(rrhh.entregas),
        PreciosSimulados(),
        int(os.getenv("SJ_EPP_MUESTRA_MINIMA") or "5"),
    )
    fuente_legajos = FuenteLegajosDesdePuerto(rrhh.legajos)
    legajo = GestionarLegajo(
        fuente_legajos,
        AdjuntosCifradosSQLite(clave_adjuntos, ruta_modulos),
    )
    configurar_personal_bot(legajo.buscar, legajo.legajos.obtener)
    salud = GestionarSalud(
        CatalogoDiagnosticoSQLite(ruta_modulos), SaludSQLite(ruta_modulos),
        AdjuntosSaludCifradosSQLite(clave_adjuntos, ruta_modulos), FuenteLaboralSimulada(),
        fuente_legajos,
    )
    turnos = ConciliarTurnos(
        FuenteFichadasSQLite(ruta_modulos),
        ExportadorArchivoLocal(Path("var/turnos/bandeja")),
        estado=EstadoTurnosSQLite(ruta_modulos),
    )
    raiz_modulos = Path(__file__).parents[1] / "modulos"
    perfiles_seleccion = CriteriosPerfilYAML(
        raiz_modulos / "seleccion" / "data" / "criterios_perfil.yaml"
    )
    configuracion_capacitacion = ConfiguracionCapacitacionYAML(
        raiz_modulos / "capacitacion" / "data" / "configuracion.yaml"
    )
    correo_rrhh = None
    clave_parametros = os.getenv("SJ_CLAVE_PARAMETROS", "").strip()
    # Sólo en desarrollo se acepta la clave de prueba; cualquier otro entorno exige la propia.
    if clave_parametros or entorno in {"desarrollo", "development", "dev", "local", "prueba", "test"}:
        correo_rrhh = construir_correo(ruta_modulos, clave_parametros or clave_adjuntos.decode(), entorno)
        if os.getenv("SJ_CORREO_CV_AUTOMATICO", "1").strip() not in {"0", "false", "no"}:
            lectura_nocturna.iniciar(correo_rrhh, int(os.getenv("SJ_CORREO_CV_HORA") or "2"))
    dsn_fila = (os.getenv("SJ_FILA_DSN_DMZ_LECTURA") or "").strip()

    def aviso_desde_rrhh(destino: str, asunto: str, cuerpo: str) -> bool:
        return correo_rrhh.enviar_aviso(destino, asunto, cuerpo) if correo_rrhh else False

    # Los correos de «¿Olvidaste tu contraseña?» salen por la misma casilla (ENAV y si no, JUBIAR).
    configurar_envio_correo(aviso_desde_rrhh)
    mosto = GestionarMosto(MostoSQLite(ruta_modulos), (
        # El aviso por mail sale desde la casilla de RRHH cargada en Parámetros.
        avisos_mosto.CorreoDesdeRRHH(aviso_desde_rrhh),
        avisos_mosto.WhatsappPorBot((os.getenv("SJ_FILA_DSN_DMZ_LECTURA") or "").strip()),
    ))
    if os.getenv("SJ_ALARMA_MOSTO", "1").strip() not in {"0", "false", "no"}:
        avisos_mosto.iniciar(mosto)
    controles = construir_controles_arca(ruta_modulos, clave_parametros, entorno, clave_adjuntos.decode())
    return {
        "parametros": crear_router_parametros(correo_rrhh, entorno),
        "epp-analitica": crear_analitica(analitica, entorno, NombresDesdePuerto(rrhh)),
        "legajo": crear_legajo(legajo, entorno),
        "salud": crear_salud(salud, entorno),
        "turnos": crear_turnos(turnos, entorno),
        "seleccion": crear_seleccion(perfiles_seleccion, entorno, ruta_modulos),
        "capacitaciones": crear_capacitacion(
            configuracion_capacitacion, entorno, ruta_modulos, fuente_legajos
        ),
        "activos": crear_activos(
            entorno, ruta_modulos, puerta=PuertaDMZ(dsn_fila) if dsn_fila else None,
            sincronizar_cada=60 if dsn_fila and os.getenv("SJ_SINCRONIZAR_REMITOS", "1").strip() not in {"0", "false", "no"}
            else None),
        "mosto": crear_mosto(mosto, entorno),
        "controles-arca": crear_controles_arca(controles, entorno),
        "rrhh-whatsapp": crear_rrhh_whatsapp(
            construir_bandeja_rrhh(entorno, ruta_modulos, clave_adjuntos, dsn_fila, legajo, salud), entorno,
            sincronizar_cada=60 if dsn_fila and os.getenv("SJ_SINCRONIZAR_RRHH_WHATSAPP", "1").strip()
            not in {"0", "false", "no"} else None),
    }


class SaludParaBandeja:
    """La bandeja de RRHH carga en Salud sin ver el catálogo ni los diagnósticos."""

    def __init__(self, salud: GestionarSalud) -> None:
        self._salud = salud

    def cargar(self, legajo, diagnostico_codigo, desde, hasta, dias, profesional, nombre_adjunto, contenido,
               resumen, tipo_accidente) -> str:
        return self._salud.cargar(legajo, diagnostico_codigo, desde, hasta, dias, profesional, nombre_adjunto,
                                  contenido, resumen, tipo_accidente).id

    def auditar(self, actor: str, legajo: str | None, accion: str) -> None:
        self._salud.auditar(actor, legajo, accion)


def construir_bandeja_rrhh(entorno: str, ruta_modulos: str, clave_adjuntos: bytes, dsn_fila: str,
                           legajo: GestionarLegajo, salud: GestionarSalud) -> BandejaRRHH:
    """Certificados y pedidos de EPP del personal, CV por WhatsApp y recorridos del micro (infra/042)."""
    # Mandar un certificado a la IA externa saca datos de salud de la empresa y acá corre solo, sin
    # nadie que lo dispare: sólo con autorización expresa en el servidor, en cualquier entorno.
    ia_externa_permitida = os.getenv("SJ_SALUD_IA_EXTERNA_AUTORIZADA", "").strip().lower() in {"1", "true", "si"}

    def leer_certificado(nombre: str, contenido: bytes, legajo_empleado: str) -> dict:
        externa = ia_externa_permitida and usaria_ia_externa(nombre)
        salud.auditar("bandeja-rrhh-whatsapp", legajo_empleado,
                      "ENVIO_CERTIFICADO_A_IA_EXTERNA_DEEPSEEK" if externa else "ANALISIS_CERTIFICADO")
        return analizar_certificado(nombre, contenido, permitir_ia_externa=ia_externa_permitida)

    def adjuntar(legajo_empleado: str, nombre: str, contenido: bytes, actor: str) -> str:
        return legajo.adjuntar(legajo_empleado, nombre, contenido).id

    cvs = construir_cvs_whatsapp(ruta_modulos, entorno)
    return BandejaRRHH(
        BandejaCifradaSQLite(clave_adjuntos, ruta_modulos),
        PuertaRRHHDMZ(dsn_fila) if dsn_fila else PuertaRRHHSinConfigurar(),
        leer_certificado,
        adjuntar,
        lambda cv: cvs.ejecutar(cv.telefono, cv.nombre_archivo, cv.contenido, cv.recibido_en,
                                f"{cv.telefono}:{cv.id}:{cv.recibido_en.isoformat()}"),
        {sede: NOMBRES_SEDES.get(sede, sede.replace("-", " ").title()) for sede in sedes_fila()},
        salud=SaludParaBandeja(salud),
    )


def construir_controles_arca(ruta_modulos: str, clave_parametros: str, entorno: str,
                             clave_prueba: str) -> GestionarControles:
    repo = ControlesSQLite(ruta_modulos)
    cifrador = None
    # La clave privada del certificado se guarda cifrada con SJ_CLAVE_PARAMETROS (derivación
    # propia); sólo en desarrollo y prueba se acepta la clave de prueba.
    if clave_parametros or entorno in {"desarrollo", "development", "dev", "local", "prueba", "test"}:
        cifrador = CifradorARCA.desde_secreto(clave_parametros or clave_prueba)
    controles = GestionarControles(
        repo, ConstanciaPDF(), padrones_arca.DescargaHTTP(),
        ConectorARCAWeb(repo.tickets, cifrador) if cifrador else None,
        CertificadosRSA(), cifrador,
        # Facturas sin QR: OCR en el servidor; IA externa sólo con autorización expresa.
        lector=LectorFacturasLocal(),
        # Segundo intento de leer el QR en el servidor, con códigos borrosos.
        lector_qr=LectorQRServidor(),
    )
    # Bajada diaria de los listados de ARCA; nunca en las pruebas.
    por_defecto = "0" if entorno in {"prueba", "test"} else "1"
    if os.getenv("SJ_DESCARGA_PADRONES", por_defecto).strip() not in {"0", "false", "no"}:
        padrones_arca.iniciar(controles)
    return controles
