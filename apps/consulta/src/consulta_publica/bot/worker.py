"""Worker permanente que responde por Chattigo desde la cola durable."""

from __future__ import annotations

import logging
import os
import re
import signal
import time
from datetime import UTC, datetime

import psycopg
from consulta_publica.lectura.repositorio_descargas import RepositorioDescargasPg

from . import transporte
from .archivos import nombre_reporte, preparar
from .chattigo import ErrorChattigo
from .conversacion import ZONA
from .conversacion import intencion as intencion_legacy
from .conversacion import responder as responder_legacy
from .dialogo import (
    CADUCADO,
    COMPROBANTE,
    DESVINCULAR,
    ESTADISTICAS,
    REPORTE,
    VINCULAR,
    responder,
)
from .estadisticas import formatear_kg, resumir
from .graficos import generar as generar_grafico
from .plantillas import LLEGADA_MICRO, armar
from .reporte_pdf import generar as generar_reporte
from .reporte_pdf import generar_comprobante, nombre_comprobante
from .repositorio import RepositorioBot

log = logging.getLogger("bot.worker")
MAX_INTENTOS = 5
_seguir = True
TIPOS_PERSONAL = {"personal": "Personal", "mando_medio": "Mando medio"}


def saludo_personal(persona) -> str:
    """Saludo al personal con lo que puede hacer por el bot."""
    nombre = persona.nombre.split(",")[-1].strip().split(" ")[0].title() or persona.nombre
    tipo = TIPOS_PERSONAL.get(persona.tipo, persona.tipo)
    return f"Hola, {nombre} ({tipo}, {persona.empresa}).\n{AYUDA_PERSONAL}"


PALABRAS_MANTENIMIENTO = ("salida", "sale ", "mantenimiento", "taller", "remito")
# RRHH (infra/042): el certificado médico y el pedido de EPP se reconocen por estas palabras.
PALABRAS_CERTIFICADO = re.compile(r"\b(certificados?|m[eé]dic[oa]s?|reposo|licencias?)\b", re.IGNORECASE)
PALABRAS_EPP = re.compile(
    r"\b(epp|guantes?|botin(es)?|botín|calzado|cascos?|ropa|anteojos?|protector(es)?)\b", re.IGNORECASE)
TIPOS_FOTO = {"image/jpeg", "image/png", "image/webp"}
MINIMO_ARCHIVO, MAXIMO_ARCHIVO = 200, 5_000_000  # certificados y CV (los mismos topes que infra/042)
EXTENSIONES = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
AYUDA_MANTENIMIENTO = ("Para registrar una salida de Mantenimiento mandá una foto con un texto, "
                       "por ejemplo: «BOM-0003 sale a Taller Pérez para bobinar».")
AYUDA_PERSONAL = ("Por este WhatsApp podés mandar:\n"
                  f"• Mantenimiento: {AYUDA_MANTENIMIENTO}\n"
                  "• Certificado médico: la foto o el PDF con la palabra «certificado».\n"
                  "• Pedido de EPP: lo que necesitás con la palabra «EPP» (podés sumar una foto), "
                  "por ejemplo: «EPP: guantes talle 9».")
PEDIR_PALABRA = ("Recibimos el archivo, pero no sabemos para qué es. Mandalo de nuevo con una palabra "
                 "que lo indique: «mantenimiento», «certificado» (médico) o «EPP».")
PEDIR_CERTIFICADO = "Para el certificado médico mandá la foto o el PDF con la palabra «certificado»."
FORMATO_NO_ADMITIDO = "Ese archivo no se puede recibir: mandá un PDF o una foto (JPG o PNG)."
CV_RECIBIDO = "Recibimos tu CV. Gracias por postularte: lo revisa Recursos Humanos."
CONFIRMADO = "Gracias, quedó confirmado. RRHH revisa el certificado."
PEDIR_CORRECCION = "Escribí en un mensaje los días correctos (o lo que esté mal) y se lo pasamos a RRHH."
CORRECCION_RECIBIDA = "Gracias, le pasamos tu corrección a RRHH, que revisa el certificado."


# Texto del aviso del micro: el mismo de la plantilla llegada_micro (por Meta sale la plantilla con
# el recorrido como parámetro; este texto es para el simulador, Chattigo o si Meta la rechaza).
def texto_aviso_micro(recorrido: str) -> str:
    return LLEGADA_MICRO.texto([recorrido])


def _con_archivo(pendiente) -> bool:
    return getattr(pendiente, "tipo", "text") in {"image", "document"} or bool(getattr(pendiente, "media_id", None))


def destino_personal(pendiente) -> str:
    """certificado, epp, mantenimiento, sin_palabra (mandó un archivo sin decir para qué) o saludo."""
    texto = pendiente.texto or ""
    if PALABRAS_CERTIFICADO.search(texto):
        return "certificado"
    if PALABRAS_EPP.search(texto):
        return "epp"
    if any(p in texto.casefold() for p in PALABRAS_MANTENIMIENTO):
        return "mantenimiento"
    return "sin_palabra" if _con_archivo(pendiente) else "saludo"


def es_para_mantenimiento(pendiente) -> bool:
    return destino_personal(pendiente) == "mantenimiento"


def tipo_real(contenido: bytes) -> str | None:
    """Tipo del archivo por sus primeros bytes, no por lo que dice el mensaje."""
    if contenido.startswith(b"%PDF-"):
        return "application/pdf"
    if contenido.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp"
    return None


def bajar_archivo(salida, pendiente) -> tuple[bytes | None, str | None, str]:
    """(contenido, tipo, aviso). Sólo PDF, JPG, PNG o WEBP de hasta 5 MB."""
    if not getattr(pendiente, "media_id", None):
        return None, None, FORMATO_NO_ADMITIDO if _con_archivo(pendiente) else ""
    try:
        contenido, _ = salida.descargar_media(pendiente.media_id, maximo=MAXIMO_ARCHIVO)
    except (ErrorChattigo, transporte.ErrorTransporte, AttributeError, OSError) as exc:
        log.warning("no se pudo bajar el archivo de %s: %s", pendiente.id, exc)
        return None, None, "El archivo no se pudo bajar (puede ser muy grande): mandalo de nuevo."
    tipo = tipo_real(contenido)
    if tipo is None or not MINIMO_ARCHIVO <= len(contenido) <= MAXIMO_ARCHIVO:
        return None, None, FORMATO_NO_ADMITIDO
    return contenido, tipo, ""


def _nombre_archivo(pendiente, tipo: str, base: str) -> str:
    return (getattr(pendiente, "media_nombre", None) or f"{base}.{EXTENSIONES[tipo]}")[:120]


def registrar_rrhh(bot, salida, pendiente, tipo: str) -> str:
    """Certificado médico o pedido de EPP: queda pendiente de revisión en la bandeja de RRHH."""
    texto = (pendiente.texto or "").strip()
    archivo, archivo_tipo, aviso = (None, None, "")
    if _con_archivo(pendiente):
        archivo, archivo_tipo, aviso = bajar_archivo(salida, pendiente)
    if tipo == "certificado" and archivo is None:
        return f"{aviso}\n{PEDIR_CERTIFICADO}".strip()
    nombre = _nombre_archivo(pendiente, archivo_tipo, tipo) if archivo_tipo else None
    try:
        numero = bot.registrar_rrhh(pendiente.telefono, tipo, texto, archivo, archivo_tipo, nombre)
    except ValueError as exc:
        return f"No se pudo registrar: {exc}."
    if tipo == "certificado":
        return (f"Listo, recibimos tu certificado médico (N.º {numero}). Queda para revisión de RRHH; "
                "en unos minutos te escribimos para confirmar los datos.")
    aviso = f"\n{aviso}" if aviso else ""
    return f"Listo, tu pedido de EPP quedó registrado (N.º {numero}). Lo revisa RRHH.{aviso}"


def registrar_cv(bot, salida, pendiente) -> str:
    """Un número que no es productor ni personal manda un archivo: es un CV para Selección."""
    contenido, tipo, aviso = bajar_archivo(salida, pendiente)
    if contenido is None or tipo is None:
        return aviso
    try:
        bot.registrar_cv(pendiente.telefono, _nombre_archivo(pendiente, tipo, "cv-whatsapp"), contenido, tipo)
    except ValueError as exc:
        return f"No se pudo recibir el CV: {exc}."
    return CV_RECIBIDO


def _si_o_no(texto: str) -> str | None:
    palabras = re.sub(r"[^\w]+", " ", texto.casefold()).split()
    if not palabras or len(palabras) > 4:
        return None
    if palabras[0] in {"1", "si", "sí"}:
        return "si"
    if palabras[0] in {"2", "no"}:
        return "no"
    return None


def responder_confirmacion(bot, pendiente) -> str | None:
    """Respuesta del empleado a lo que se leyó de su certificado. None: no era una respuesta."""
    texto = (pendiente.texto or "").strip()
    if not hasattr(bot, "confirmacion_pendiente") or _con_archivo(pendiente) or not texto:
        return None
    estado = bot.confirmacion_pendiente(pendiente.telefono)
    if estado == "esperando":
        respuesta = _si_o_no(texto)
        nuevo = bot.responder_certificado(pendiente.telefono, respuesta) if respuesta else None
        return {"confirmado": CONFIRMADO, "corrigiendo": PEDIR_CORRECCION}.get(nuevo or "")
    if estado == "corrigiendo":
        nuevo = bot.responder_certificado(pendiente.telefono, "correccion", texto)
        return CORRECCION_RECIBIDA if nuevo == "no_coincide" else None
    return None


def respuesta_personal(bot, salida, pendiente, persona) -> tuple[str, bool]:
    """(texto, registró algo). Lo que se registró no se reintenta: quedaría dos veces."""
    confirmacion = responder_confirmacion(bot, pendiente)
    if confirmacion is not None:
        return confirmacion, True
    destino = destino_personal(pendiente)
    if destino in {"certificado", "epp"} and hasattr(bot, "registrar_rrhh"):
        return registrar_rrhh(bot, salida, pendiente, destino), True
    if destino == "mantenimiento" and hasattr(bot, "registrar_mantenimiento"):
        return registrar_mantenimiento(bot, salida, pendiente), True
    if destino == "sin_palabra":
        return PEDIR_PALABRA, False
    return saludo_personal(persona), False


def registrar_mantenimiento(bot, salida, pendiente) -> str:
    """Foto y texto del personal: quedan para el Encargado de Mantenimiento en Gestión."""
    foto, tipo, aviso = None, None, ""
    media_id = getattr(pendiente, "media_id", None)
    if media_id:
        try:
            contenido, tipo_recibido = salida.descargar_media(media_id)
            if tipo_recibido in TIPOS_FOTO and 1000 <= len(contenido) <= 3_000_000:
                foto, tipo = contenido, tipo_recibido
            else:
                aviso = "\nLa foto no se pudo guardar (formato o tamaño): mandala de nuevo."
        except (ErrorChattigo, transporte.ErrorTransporte, AttributeError, OSError) as exc:
            log.warning("no se pudo bajar la foto de %s: %s", pendiente.id, exc)
            aviso = "\nLa foto no se pudo bajar: mandala de nuevo."
    texto = (pendiente.texto or "").strip()
    if not foto and not texto:
        return AYUDA_MANTENIMIENTO + aviso
    try:
        numero = bot.registrar_mantenimiento(pendiente.telefono, texto, foto, tipo)
    except ValueError as exc:
        return f"No se pudo registrar: {exc}."
    return f"Listo, quedó registrado para Mantenimiento (N.º {numero}). El Encargado lo revisa en Gestión.{aviso}"


def _max_respuestas_hora() -> int:
    valor = int(os.environ.get("BOT_MAX_RESPUESTAS_HORA", "20"))
    if valor < 1:
        raise RuntimeError("BOT_MAX_RESPUESTAS_HORA debe ser mayor que cero")
    return valor


def _parar(*_: object) -> None:
    global _seguir
    _seguir = False


def procesar_una_vez(bot: RepositorioBot, consultas, salida, maximo_hora: int = 20) -> int:
    pendientes = bot.tomar()
    hoy = transporte.fecha_hoy()
    # Conserva el contrato anterior durante despliegues escalonados y para los
    # adaptadores que todavía exponen ``productores`` en vez de sesiones.
    if not hasattr(bot, "cuentas"):
        return _procesar_legacy(bot, consultas, salida, pendientes, hoy, maximo_hora)
    base_archivos = os.environ.get("BOT_PUBLIC_BASE_URL", "").strip()
    if not base_archivos.startswith("https://"):
        raise RuntimeError("BOT_PUBLIC_BASE_URL tiene que ser HTTPS")
    bot.limpiar_archivos()
    for pendiente in pendientes:
        if bot.respuestas_ultima_hora(pendiente.telefono) >= maximo_hora:
            bot.cerrar(pendiente.id, "ignorado", error="tope de respuestas por hora")
            continue
        # El personal de la empresa no entra al menú de productores (un celular es de uno o
        # de otro, nunca de los dos: infra/034).
        persona = bot.personal(pendiente.telefono) if hasattr(bot, "personal") else None
        if persona is not None:
            try:
                texto, registro = respuesta_personal(bot, salida, pendiente, persona)
            except (psycopg.Error, OSError) as exc:  # no quedó nada registrado: se puede reintentar
                bot.reintentar(pendiente.id, str(exc), MAX_INTENTOS)
                log.warning("no se pudo registrar el mensaje del personal (intento %s): %s",
                            pendiente.intentos + 1, exc)
                continue
            try:
                wamid = salida.enviar_texto(pendiente.telefono, texto)
            except (ErrorChattigo, transporte.ErrorTransporte, psycopg.Error, RuntimeError,
                    ValueError, OSError) as exc:
                if registro:
                    # Ya quedó registrado: reintentar lo registraría dos veces. Se cierra sin respuesta.
                    bot.cerrar(pendiente.id, "error", respuesta=texto, error=f"registrado; falló la respuesta: {exc}")
                else:
                    bot.reintentar(pendiente.id, str(exc), MAX_INTENTOS)
                log.warning("envío falló (intento %s): %s", pendiente.intentos + 1, exc)
                continue
            bot.cerrar(pendiente.id, "respondido", respuesta=texto, wamid_salida=wamid)
            continue
        cuentas = bot.cuentas(pendiente.telefono)
        # Un número sin alta puede estar vinculado a una cuenta por cuenta, CUIT o patente.
        vinculada = bot.vinculo(pendiente.telefono) if not cuentas and hasattr(bot, "vinculo") else None
        if not cuentas and _con_archivo(pendiente) and hasattr(bot, "registrar_cv"):
            # Ni productor ni personal: el archivo es un CV para Selección (infra/042).
            try:
                texto = registrar_cv(bot, salida, pendiente)
            except (psycopg.Error, OSError) as exc:  # no quedó nada registrado: se puede reintentar
                bot.reintentar(pendiente.id, str(exc), MAX_INTENTOS)
                log.warning("no se pudo registrar el CV (intento %s): %s", pendiente.intentos + 1, exc)
                continue
            try:
                wamid = salida.enviar_texto(pendiente.telefono, texto)
            except (ErrorChattigo, transporte.ErrorTransporte, psycopg.Error, RuntimeError,
                    ValueError, OSError) as exc:
                # Ya quedó registrado: reintentar lo registraría dos veces.
                bot.cerrar(pendiente.id, "error", respuesta=texto, error=f"registrado; falló la respuesta: {exc}")
                continue
            bot.cerrar(pendiente.id, "respondido", respuesta=texto, wamid_salida=wamid)
            continue
        abierta = vinculada is not None
        if abierta:
            # Sólo consulta: estadísticas, informe y comprobantes (nada de turnos ni contactos).
            cuentas, permisos = [vinculada], {"ver_informes"}
        else:
            permisos = bot.permisos(pendiente.telefono) if cuentas else set()
        estado, caducada = bot.estado_y_caducidad(pendiente.telefono)
        # Quien todavía se está identificando no pierde lo que escribió porque pasó un rato.
        caducada = caducada and bool(cuentas)
        try:
            identificar, candidatas = None, []
            if not cuentas and hasattr(bot, "identificador"):
                identificar = bot.identificador(pendiente.telefono)
                candidatas = bot.cuentas_por_cuit(estado.candidatas) if estado.candidatas else []
            # El pedido de turno lee y reserva en la base desde el diálogo: si la base
            # falla a mitad de camino, el mensaje se reintenta como cualquier envío.
            respuesta = responder(
                "hola" if caducada else pendiente.texto,
                cuentas,
                estado,
                hoy,
                puede_ver_informes="ver_informes" in permisos,
                puede_administrar="administrar_contactos" in permisos,
                puede_pedir_turnos="pedir_turnos" in permisos,
                turnos=(bot.turnos(pendiente.telefono)
                        if hasattr(bot, "turnos") and cuentas and not abierta else None),
                # Los turnos van siempre con la fecha real, aunque haya BOT_FECHA_SIMULADA.
                hoy_turnos=datetime.now(ZONA).date(),
                sesion_abierta=abierta,
                identificar=identificar,
                candidatas=candidatas,
            )
            if caducada:
                respuesta.texto = f"{CADUCADO}\n\n{respuesta.texto}"
        except Exception as exc:  # noqa: BLE001 - un mensaje con problemas no frena a los demás
            bot.reintentar(pendiente.id, str(exc), MAX_INTENTOS)
            log.warning("diálogo falló (intento %s): %s", pendiente.intentos + 1, exc)
            continue
        # A partir de acá el diálogo ya pudo haber reservado un turno: nunca se reintenta el
        # mensaje (eso lo reservaría de nuevo). Si no se guarda la sesión, se sigue igual.
        try:
            bot.guardar_estado(pendiente.telefono, respuesta.estado)
        except (psycopg.Error, OSError) as exc:
            log.warning("no se pudo guardar la sesión de %s: %s", pendiente.id, exc)
        try:
            texto, wamid = ejecutar(bot, consultas, salida, pendiente.telefono, respuesta,
                                    base_archivos, abierta)
        except (
            ErrorChattigo,
            transporte.ErrorTransporte,
            psycopg.Error,
            RuntimeError,
            ValueError,
            OSError,
        ) as exc:
            bot.reintentar(pendiente.id, str(exc), MAX_INTENTOS)
            log.warning("envío falló (intento %s): %s", pendiente.intentos + 1, exc)
            continue
        bot.cerrar(pendiente.id, "respondido", respuesta=texto, wamid_salida=wamid)
    return len(pendientes) + enviar_avisos(bot, salida) + enviar_avisos_personal(bot, salida)


def enviar_respuesta(salida, telefono: str, respuesta) -> tuple[str, str]:
    """(texto que queda en la cola, wamid). Por Meta, las opciones van como botones o lista;
    en el simulador y por Chattigo, como texto numerado (el diálogo entiende las dos)."""
    texto = respuesta.con_botones()
    if respuesta.opciones and hasattr(salida, "enviar_opciones"):
        return texto, salida.enviar_opciones(telefono, respuesta.texto, respuesta.opciones, respuesta.desde)
    return texto, salida.enviar_texto(telefono, texto)


def _registrar(bot, clientecuit: str, recurso: str, filas: int, telefono: str | None) -> None:
    """Las consultas de un número vinculado sin alta quedan en la bitácora con el teléfono."""
    if telefono is None:
        bot.registrar_consulta(clientecuit, recurso, filas)
    else:
        bot.registrar_consulta(clientecuit, recurso, filas, telefono)


def enviar_comprobante(bot, consultas, salida, telefono: str, cuenta, ciu: str | None, base_archivos: str,
                       telefono_bitacora: str | None, avisar_si_falta: bool = True) -> tuple[str | None, str | None]:
    """DDJJ – Comprobante de Ingreso de Uva de una descarga de la cuenta activa: la del CIU pedido
    o la última. (texto, wamid); (None, None) si no hay y no hace falta avisar."""
    comprobante = consultas.comprobante(cuenta.clientecuit, ciu, cuenta.titular, cuenta.codigo)
    if comprobante is None:
        if not avisar_si_falta:
            return None, None
        texto = (f"No encontré el comprobante N.º {ciu} en la cuenta {cuenta.codigo}.\n"
                 "Revisá el número; sólo se ven las descargas de esta cuenta." if ciu
                 else f"Todavía no hay descargas en la cuenta {cuenta.codigo}.")
        return texto, salida.enviar_texto(telefono, texto)
    nombre = nombre_comprobante(comprobante)
    archivo = preparar(generar_comprobante(comprobante), "pdf", nombre, datetime.now(UTC))
    bot.guardar_archivo(archivo, telefono)
    texto = (f"DDJJ – Comprobante de Ingreso de Uva\nCIU {comprobante.ciu} · "
             f"{formatear_kg(comprobante.neto)}\nPara otro comprobante, escribí su número de CIU.")
    wamid = salida.enviar_documento(telefono, archivo.url(base_archivos), nombre, texto)
    _registrar(bot, cuenta.clientecuit, "whatsapp:comprobante", 1, telefono_bitacora)
    return texto, wamid


def ejecutar(bot, consultas, salida, telefono: str, respuesta, base_archivos: str,
             abierta: bool = False) -> tuple[str, str]:
    """Hace lo que pidió el diálogo y responde. (texto que queda en la cola, wamid)."""
    bitacora = telefono if abierta or respuesta.accion == VINCULAR else None
    if respuesta.accion == VINCULAR:
        # Como el bot anterior: al identificarse llega el comprobante de la última descarga.
        bot.vincular(telefono, respuesta.cuenta)
        _registrar(bot, respuesta.cuenta.clientecuit, "whatsapp:vincular", 1, telefono)
        if hasattr(consultas, "comprobante"):
            enviar_comprobante(bot, consultas, salida, telefono, respuesta.cuenta, None, base_archivos,
                               telefono, avisar_si_falta=False)
        return enviar_respuesta(salida, telefono, respuesta)
    if respuesta.accion == DESVINCULAR:
        bot.desvincular(telefono)
        return enviar_respuesta(salida, telefono, respuesta)
    if respuesta.accion == COMPROBANTE:
        texto, wamid = enviar_comprobante(bot, consultas, salida, telefono, respuesta.cuenta, respuesta.ciu,
                                          base_archivos, bitacora)
        return texto or "", wamid or ""
    if respuesta.accion not in {ESTADISTICAS, REPORTE}:
        return enviar_respuesta(salida, telefono, respuesta)
    entregas = consultas.entregas(
        respuesta.cuenta.clientecuit,
        respuesta.periodo.desde,
        respuesta.periodo.hasta,
    )
    if not entregas:
        texto = "No hay entregas en ese período."
        return texto, salida.enviar_texto(telefono, texto)
    resumen = resumir(entregas)
    ahora = datetime.now(UTC)
    if respuesta.accion == ESTADISTICAS:
        contenido = generar_grafico(
            resumen,
            respuesta.cuenta.titular,
            respuesta.cuenta.codigo,
            respuesta.periodo.etiqueta,
        )
        archivo = preparar(contenido, "png", "estadisticas.png", ahora)
        bot.guardar_archivo(archivo, telefono)
        texto = (
            f"Estadísticas de cosecha - {respuesta.periodo.etiqueta}\n"
            f"Total: {resumen.total_kg:,} kg"
        ).replace(",", ".")
        wamid = salida.enviar_imagen(telefono, archivo.url(base_archivos), texto)
    else:
        nombre = nombre_reporte(
            respuesta.cuenta.codigo,
            respuesta.periodo.desde,
            respuesta.periodo.hasta,
        )
        contenido = generar_reporte(
            entregas,
            resumen,
            respuesta.cuenta.titular,
            respuesta.cuenta.codigo,
            respuesta.periodo.etiqueta,
        )
        archivo = preparar(contenido, "pdf", nombre, ahora)
        bot.guardar_archivo(archivo, telefono)
        texto = (
            f"Detalle de cosecha - {respuesta.cuenta.titular.strip().rstrip('.')}\n"
            f"Total: {resumen.total_kg:,} kg ({resumen.entregas} entregas)"
        ).replace(",", ".")
        wamid = salida.enviar_documento(telefono, archivo.url(base_archivos), nombre, texto)
    _registrar(bot, respuesta.cuenta.clientecuit, f"whatsapp:{respuesta.accion}", len(entregas), bitacora)
    return texto, wamid


def enviar_avisos(bot, salida) -> int:
    """Avisos que dejó la bodega al asignar o postergar días (infra/038) y el de mosto virgen
    (infra/040). Desde infra/043 traen la plantilla de Meta y sus parámetros.

    Devuelve cuántos salieron: los que fallan esperan 10 minutos y no cuentan como trabajo
    hecho, así el ciclo principal no se queda girando sin pausa."""
    if not hasattr(bot, "tomar_avisos"):
        return 0
    return _enviar_cola(bot.tomar_avisos, bot.marcar_aviso, salida, lambda aviso: aviso["texto"],
                        lambda aviso: (aviso.get("plantilla"), aviso.get("parametros")))


def enviar_avisos_personal(bot, salida) -> int:
    """Mensajes al personal (infra/042): llegó el micro de su recorrido, o lo que se leyó de su
    certificado para que lo confirme. Se manejan igual que los avisos de la bodega. La lectura del
    certificado contesta lo que mandó el empleado (dentro de las 24 h): no lleva plantilla."""
    if not hasattr(bot, "tomar_avisos_personal"):
        return 0

    def texto(aviso: dict) -> str:
        return texto_aviso_micro(aviso["recorrido"]) if aviso["tipo"] == "micro" else aviso["texto"]

    def plantilla(aviso: dict) -> tuple[str | None, list | None]:
        if aviso["tipo"] == "micro":
            return LLEGADA_MICRO.nombre, [aviso["recorrido"]]
        return None, None

    return _enviar_cola(bot.tomar_avisos_personal, bot.marcar_aviso_personal, salida, texto, plantilla)


def enviar_aviso(salida, telefono: str, texto: str, nombre: str | None, parametros) -> tuple[str, str | None]:
    """(wamid, nota). Por Meta, con plantilla si el aviso la trae; si Meta no la acepta (todavía
    no está aprobada, por ejemplo) sale el texto y la nota lo deja anotado. En el simulador y por
    Chattigo, siempre el texto, como antes."""
    armada = armar(nombre, parametros) if hasattr(salida, "enviar_plantilla") else None
    if armada is None:
        return salida.enviar_texto(telefono, texto), None
    plantilla, valores = armada
    try:
        return salida.enviar_plantilla(telefono, plantilla.nombre, plantilla.idioma, valores), None
    except ErrorChattigo as exc:
        # Cualquier rechazo de la plantilla (no aprobada, parámetros, códigos que Meta cambie):
        # el aviso sale igual como texto, que llega si la persona escribió en las últimas 24 h.
        codigo = getattr(exc, "codigo", None)
        log.warning("plantilla %s no salió (%s): sale como texto", plantilla.nombre, codigo)
        nota = f"plantilla {plantilla.nombre} rechazada ({codigo}); salió como texto"
        return salida.enviar_texto(telefono, texto), nota


def _enviar_cola(tomar, marcar, salida, texto_de, plantilla_de) -> int:
    try:
        avisos = tomar()
    except psycopg.Error as exc:  # base sin la migración todavía: no frena las respuestas
        log.warning("no se pudieron leer los avisos: %s", exc.__class__.__name__)
        return 0
    enviados = 0
    for aviso in avisos:
        nota = None
        try:
            wamid, nota = enviar_aviso(salida, aviso["telefono"], texto_de(aviso), *plantilla_de(aviso))
            error = None
            enviados += 1
        except (ErrorChattigo, transporte.ErrorTransporte, RuntimeError, ValueError, OSError) as exc:
            wamid, error = None, str(exc)
            log.warning("aviso %s no salió: %s", aviso["id"], exc)
        # Si ya salió y no se puede anotar, se insiste: si no, se reenviaría al vencer la reserva.
        # Una falla sin anotar no hace falta reintentarla: igual espera la reserva.
        intentos = 3 if error is None else 1
        for intento in range(intentos):
            try:
                if nota:
                    marcar(aviso["id"], wamid, error, nota)
                else:
                    marcar(aviso["id"], wamid, error)
                break
            except psycopg.Error as exc:
                log.warning("no se pudo marcar el aviso %s (intento %s): %s",
                            aviso["id"], intento + 1, exc.__class__.__name__)
                if intento + 1 < intentos and _seguir:
                    time.sleep(0.5 * (intento + 1))
    return enviados


def _procesar_legacy(bot, consultas, salida, pendientes, hoy, maximo_hora: int) -> int:
    for pendiente in pendientes:
        if bot.respuestas_ultima_hora(pendiente.telefono) >= maximo_hora:
            bot.cerrar(pendiente.id, "ignorado", error="tope de respuestas por hora")
            continue
        productores = bot.productores(pendiente.telefono)
        texto = responder_legacy(pendiente.texto, productores, consultas, hoy)
        try:
            wamid = salida.enviar_texto(pendiente.telefono, texto)
        except (ErrorChattigo, transporte.ErrorTransporte) as exc:
            bot.reintentar(pendiente.id, str(exc), MAX_INTENTOS)
            continue
        bot.cerrar(pendiente.id, "respondido", respuesta=texto, wamid_salida=wamid)
        for clientecuit in productores:
            bot.registrar_consulta(
                clientecuit, f"whatsapp:{intencion_legacy(pendiente.texto)}", 0
            )
    return len(pendientes)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    signal.signal(signal.SIGTERM, _parar)
    signal.signal(signal.SIGINT, _parar)
    dsn = os.environ["BOT_DSN"]
    bot = RepositorioBot(dsn)
    consultas = RepositorioDescargasPg(dsn)
    salida = transporte.desde_entorno()
    transporte.fecha_hoy()
    log.info("transporte: %s", transporte.modo())
    maximo_hora = _max_respuestas_hora()
    while _seguir:
        try:
            if procesar_una_vez(bot, consultas, salida, maximo_hora) == 0:
                time.sleep(1.5)
        except Exception:
            log.exception("ciclo falló; se reintenta en 10 s")
            time.sleep(10)


if __name__ == "__main__":
    main()
