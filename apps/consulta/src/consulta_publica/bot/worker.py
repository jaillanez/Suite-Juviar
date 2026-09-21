"""Worker permanente que responde por Chattigo desde la cola durable."""

from __future__ import annotations

import logging
import os
import signal
import time
from datetime import datetime

from consulta_publica.lectura.repositorio_descargas import RepositorioDescargasPg

from .chattigo import ClienteChattigo, ConfigChattigo, ErrorChattigo
from .conversacion import ZONA, intencion, responder
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


def procesar_una_vez(bot: RepositorioBot, consultas, chattigo, maximo_hora: int = 20) -> int:
    pendientes = bot.tomar()
    hoy = datetime.now(ZONA).date()
    for pendiente in pendientes:
        if bot.respuestas_ultima_hora(pendiente.telefono) >= maximo_hora:
            bot.cerrar(pendiente.id, "ignorado", error="tope de respuestas por hora")
            continue
        inscriptos = bot.inscriptos(pendiente.telefono)
        texto = responder(pendiente.texto, inscriptos, consultas, hoy)
        try:
            wamid = chattigo.enviar_texto(pendiente.telefono, texto)
        except ErrorChattigo as exc:
            bot.reintentar(pendiente.id, str(exc), MAX_INTENTOS)
            log.warning("envío falló (intento %s): %s", pendiente.intentos + 1, exc)
            continue
        bot.cerrar(pendiente.id, "respondido", respuesta=texto, wamid_salida=wamid)
        for inscripto in inscriptos:
            bot.registrar_consulta(inscripto, f"whatsapp:{intencion(pendiente.texto)}", 0)
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
    chattigo = ClienteChattigo(ConfigChattigo.desde_entorno())
    maximo_hora = _max_respuestas_hora()
    while _seguir:
        try:
            if procesar_una_vez(bot, consultas, chattigo, maximo_hora) == 0:
                time.sleep(1.5)
        except Exception:
            log.exception("ciclo falló; se reintenta en 10 s")
            time.sleep(10)


if __name__ == "__main__":
    main()
