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
    while True:
        publicador.publicar()
        time.sleep(300)


if __name__ == "__main__":
    main()
