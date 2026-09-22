from __future__ import annotations

import logging
import os
import time

from .repositorio import RepositorioFila

log = logging.getLogger("fila.worker")


def ejecutar(repo: RepositorioFila) -> tuple[int, int, int]:
    vencidos = repo.expirar()
    vinculados, ambiguos = repo.cerrar_con_descargas()
    return vencidos, vinculados, ambiguos


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    repo = RepositorioFila(os.environ["FILA_DSN_WORKER"])
    while True:
        try:
            vencidos, vinculados, ambiguos = ejecutar(repo)
            if vencidos or vinculados or ambiguos:
                log.info(
                    "vencidos=%s vinculados=%s ambiguos=%s",
                    vencidos,
                    vinculados,
                    ambiguos,
                )
        except Exception:
            log.exception("falló ciclo de cierre")
        time.sleep(300)


if __name__ == "__main__":
    main()
