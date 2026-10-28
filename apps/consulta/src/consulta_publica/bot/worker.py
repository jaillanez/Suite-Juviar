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
        cuentas = bot.cuentas(pendiente.telefono)
        permisos = bot.permisos(pendiente.telefono)
        estado, caducada = bot.estado_y_caducidad(pendiente.telefono)
        respuesta = responder(
            "hola" if caducada else pendiente.texto,
            cuentas,
            estado,
            hoy,
            puede_ver_informes="ver_informes" in permisos,
            puede_administrar="administrar_contactos" in permisos,
        )
        if caducada:
            respuesta.texto = f"{CADUCADO}\n\n{respuesta.texto}"
        bot.guardar_estado(pendiente.telefono, respuesta.estado)
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
    return len(pendientes)


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
