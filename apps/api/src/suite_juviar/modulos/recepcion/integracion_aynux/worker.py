"""Worker Aynux: ``python -m ...integracion_aynux.worker ventana|nocturna|inicial``."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime, timedelta

from .config import Config, Sede
from .fuente_oracle import FuenteOracle
from .planificador import planificar
from .repositorio import RepositorioDmz, RepositorioSuite

log = logging.getLogger("recepcion.integracion_aynux")
INICIO_HISTORICO = datetime(2000, 1, 1)  # noqa: DTZ001 - FECHA Oracle no tiene zona


def _desde(modo: str, config: Config) -> datetime:
    ahora = datetime.now()  # noqa: DTZ005 - hora local, igual que FECHA de Oracle
    if modo == "ventana":
        return ahora - timedelta(days=config.ventana_dias)
    if modo == "nocturna":
        return ahora - timedelta(days=config.ventana_nocturna_dias)
    if modo == "inicial":
        return INICIO_HISTORICO
    raise SystemExit(f"modo desconocido: {modo}")


def sincronizar_sede(sede: Sede, modo: str, config: Config) -> int:
    suite = RepositorioSuite(config.dsn_suite)
    dmz = RepositorioDmz(config.dsn_dmz)
    fuente = FuenteOracle(sede, config.usuario, config.clave)
    desde = _desde(modo, config)
    with suite.conectar() as conexion:
        if not suite.tomar_candado(conexion, sede.codigo):
            log.warning("%s: otra corrida en curso, se omite", sede.codigo)
            return 0
        corrida = suite.abrir_corrida(conexion, sede.codigo, modo, desde)
        leidas, plan = 0, None
        try:
            filas = fuente.leer_ventana(desde)
            leidas = len(filas)
            plan = planificar(
                filas,
                suite.estado_local(conexion, sede.codigo, desde),
                minimo_filas=config.minimo_filas,
                tope_ausencias=config.tope_ausencias,
            )
            suite.aplicar(conexion, sede.codigo, plan)
            suite.cerrar_corrida(conexion, corrida, leidas, plan, None)
        except Exception as error:
            conexion.rollback()
            suite.cerrar_corrida(
                conexion,
                corrida,
                leidas,
                plan,
                f"{type(error).__name__}: {error}"[:1000],
            )
            log.exception("%s: corrida %s falló", sede.codigo, corrida)
            return 1

        if plan.ausencias_suspendidas:
            log.error("%s: ausencias suspendidas — %s", sede.codigo, plan.ausencias_suspendidas)
        try:
            while pendientes := suite.pendientes_de_publicar(conexion):
                dmz.publicar(pendientes)
                suite.marcar_publicadas(conexion, [fila["id"] for fila in pendientes])
            dmz.registrar_sincronizacion(sede.codigo, datetime.now(UTC))
        except Exception:
            log.exception(
                "%s: publicación a DMZ falló; queda pendiente para la próxima corrida",
                sede.codigo,
            )
            return 1

    log.info(
        "%s %s: leídas=%d nuevas=%d modificadas=%d ausentes=%d",
        sede.codigo,
        modo,
        leidas,
        len(plan.nuevos),
        len(plan.modificados),
        len(plan.ausentes),
    )
    return 0


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if len(argv) != 2:
        print(__doc__)
        return 2
    config = Config.desde_entorno()
    return max((sincronizar_sede(sede, argv[1], config) for sede in config.sedes), default=0)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
