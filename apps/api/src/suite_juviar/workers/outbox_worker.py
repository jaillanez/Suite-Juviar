"""Worker de eventos de dominio.

Toma pendientes con SELECT ... FOR UPDATE SKIP LOCKED, los entrega a los
suscriptores registrados y aplica backoff exponencial. Un evento que agota los
reintentos queda FALLIDO y visible en el panel: nunca desaparece en silencio
(regla 7 de construcción).
"""

from __future__ import annotations

import asyncio
import logging

from suite_juviar.plataforma.db.base import SessionLocal
from suite_juviar.plataforma.outbox.infrastructure.repositorio import OutboxSQL

log = logging.getLogger("outbox")

SUSCRIPTORES: dict[str, list] = {
    # "recepcion.romaneo.cerrado": [proyectar_a_lectura_bot, ...]
}

INTERVALO_S = 2


async def ciclo() -> None:
    async with SessionLocal() as session:
        outbox = OutboxSQL(session)
        for entrada in await outbox.tomar_pendientes():
            try:
                for handler in SUSCRIPTORES.get(entrada.evento.nombre, []):
                    await handler(entrada.evento)
                entrada.marcar_entregado()
            except Exception as exc:
                log.exception("Fallo entregando %s", entrada.evento.nombre)
                entrada.marcar_fallo(str(exc), entrada.evento.ocurrido_en)
            await outbox.confirmar(entrada)
        await session.commit()


async def main() -> None:
    while True:
        await ciclo()
        await asyncio.sleep(INTERVALO_S)


if __name__ == "__main__":
    asyncio.run(main())
