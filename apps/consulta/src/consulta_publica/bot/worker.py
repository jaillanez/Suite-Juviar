"""Worker permanente que responde por Chattigo desde la cola durable."""

from __future__ import annotations

import logging
import os
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
from .dialogo import CADUCADO, ESTADISTICAS, responder
from .estadisticas import resumir
from .graficos import generar as generar_grafico
from .reporte_pdf import generar as generar_reporte
from .repositorio import RepositorioBot

log = logging.getLogger("bot.worker")
MAX_INTENTOS = 5
_seguir = True
TIPOS_PERSONAL = {"personal": "Personal", "mando_medio": "Mando medio"}


def saludo_personal(persona) -> str:
    """Saludo al personal con lo que puede hacer por el bot."""
    nombre = persona.nombre.split(",")[-1].strip().split(" ")[0].title() or persona.nombre
    tipo = TIPOS_PERSONAL.get(persona.tipo, persona.tipo)
    return f"Hola, {nombre} ({tipo}, {persona.empresa}).\n{AYUDA_MANTENIMIENTO}"


PALABRAS_MANTENIMIENTO = ("salida", "sale ", "mantenimiento", "taller", "remito")
TIPOS_FOTO = {"image/jpeg", "image/png", "image/webp"}
AYUDA_MANTENIMIENTO = ("Para registrar una salida de Mantenimiento mandá una foto con un texto, "
                       "por ejemplo: «BOM-0003 sale a Taller Pérez para bobinar».")


def es_para_mantenimiento(pendiente) -> bool:
    texto = (pendiente.texto or "").casefold()
    return bool(getattr(pendiente, "media_id", None)) or any(p in texto for p in PALABRAS_MANTENIMIENTO)


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
            registro = hasattr(bot, "registrar_mantenimiento") and es_para_mantenimiento(pendiente)
            if registro:
                try:
                    texto = registrar_mantenimiento(bot, salida, pendiente)
                except (psycopg.Error, OSError) as exc:  # no quedó nada registrado: se puede reintentar
                    bot.reintentar(pendiente.id, str(exc), MAX_INTENTOS)
                    log.warning("no se pudo registrar para mantenimiento (intento %s): %s",
                                pendiente.intentos + 1, exc)
                    continue
            else:
                texto = saludo_personal(persona)
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
        permisos = bot.permisos(pendiente.telefono)
        estado, caducada = bot.estado_y_caducidad(pendiente.telefono)
        try:
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
                turnos=bot.turnos(pendiente.telefono) if hasattr(bot, "turnos") else None,
                # Los turnos van siempre con la fecha real, aunque haya BOT_FECHA_SIMULADA.
                hoy_turnos=datetime.now(ZONA).date(),
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
            if respuesta.accion in {"estadisticas", "reporte"}:
                entregas = consultas.entregas(
                    respuesta.cuenta.clientecuit,
                    respuesta.periodo.desde,
                    respuesta.periodo.hasta,
                )
                if not entregas:
                    texto = "No hay entregas en ese período."
                    wamid = salida.enviar_texto(pendiente.telefono, texto)
                else:
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
                        bot.guardar_archivo(archivo, pendiente.telefono)
                        texto = (
                            f"Estadísticas de cosecha - {respuesta.periodo.etiqueta}\n"
                            f"Total: {resumen.total_kg:,} kg"
                        ).replace(",", ".")
                        wamid = salida.enviar_imagen(
                            pendiente.telefono, archivo.url(base_archivos), texto
                        )
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
                        bot.guardar_archivo(archivo, pendiente.telefono)
                        texto = (
                            f"Detalle de cosecha - {respuesta.cuenta.titular.strip().rstrip('.')}\n"
                            f"Total: {resumen.total_kg:,} kg ({resumen.entregas} entregas)"
                        ).replace(",", ".")
                        wamid = salida.enviar_documento(
                            pendiente.telefono, archivo.url(base_archivos), nombre, texto
                        )
                    bot.registrar_consulta(
                        respuesta.cuenta.clientecuit,
                        f"whatsapp:{respuesta.accion}",
                        len(entregas),
                    )
            else:
                texto = respuesta.con_botones()
                wamid = salida.enviar_texto(pendiente.telefono, texto)
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
    return len(pendientes) + enviar_avisos(bot, salida)


def enviar_avisos(bot, salida) -> int:
    """Avisos que dejó la bodega al asignar o postergar días (infra/038).

    Devuelve cuántos salieron: los que fallan esperan 10 minutos y no cuentan como trabajo
    hecho, así el ciclo principal no se queda girando sin pausa."""
    if not hasattr(bot, "tomar_avisos"):
        return 0
    try:
        avisos = bot.tomar_avisos()
    except psycopg.Error as exc:  # base sin infra/038 todavía: no frena las respuestas
        log.warning("no se pudieron leer los avisos: %s", exc.__class__.__name__)
        return 0
    enviados = 0
    for aviso in avisos:
        try:
            wamid, error = salida.enviar_texto(aviso["telefono"], aviso["texto"]), None
            enviados += 1
        except (ErrorChattigo, transporte.ErrorTransporte, RuntimeError, ValueError, OSError) as exc:
            wamid, error = None, str(exc)
            log.warning("aviso %s no salió: %s", aviso["id"], exc)
        # Si ya salió y no se puede anotar, se insiste: si no, se reenviaría al vencer la reserva.
        # Una falla sin anotar no hace falta reintentarla: igual espera la reserva.
        intentos = 3 if error is None else 1
        for intento in range(intentos):
            try:
                bot.marcar_aviso(aviso["id"], wamid, error)
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
