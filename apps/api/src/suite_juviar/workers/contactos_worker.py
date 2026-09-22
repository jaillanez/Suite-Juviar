from __future__ import annotations

import logging
import os
import time

from suite_juviar.plataforma.terceros.infrastructure.publicar_contactos import (
    PublicadorContactos,
)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    publicador = PublicadorContactos(
        os.environ["RECEPCION_DSN_SUITE"], os.environ["RECEPCION_DSN_DMZ"]
    )
    proxima_copia_productores = 0.0
    while True:
        publicador.publicar()
        if time.monotonic() >= proxima_copia_productores:
            publicador.publicar_productores()
            proxima_copia_productores = time.monotonic() + 24 * 60 * 60
        time.sleep(300)


if __name__ == "__main__":
    main()
