"""Composition root: recepción de uva de un productor tercero.

Cruza recepción con el registro de terceros por un motivo legal, no técnico:
bajo la Ley 9133 de Mendoza, si la bodega procesa uva de terceros sin verificar
la registración y la entrega de EPP de los trabajadores de ese productor, puede
ser declarada solidariamente responsable de sus multas.

PENDIENTE §7.1: definir con el asesor legal qué documentación se exige y qué
queda registrado. Hasta entonces el flujo advierte y deja constancia, pero no
bloquea: bloquear la descarga de un camión en plena vendimia con un criterio no
validado sería peor que el riesgo que evita.
"""

from __future__ import annotations

from datetime import UTC, datetime

from suite_juviar.modulos.recepcion.application.casos_uso import AbrirRomaneo, DatosIngreso
from suite_juviar.modulos.recepcion.domain.eventos import RECEPCION_PRODUCTOR_SIN_VERIFICACION
from suite_juviar.plataforma.outbox.domain.entidades import EventoDeDominio
from suite_juviar.plataforma.outbox.domain.puertos import Outbox
from suite_juviar.plataforma.terceros.domain.entidades import CUIT
from suite_juviar.plataforma.terceros.domain.puertos import RepositorioTerceros


class RecibirUvaDeTercero:
    def __init__(
        self, terceros: RepositorioTerceros, abrir: AbrirRomaneo, outbox: Outbox
    ) -> None:
        self._terceros = terceros
        self._abrir = abrir
        self._outbox = outbox

    async def __call__(self, datos: DatosIngreso):
        productor = await self._terceros.obtener(CUIT(datos.productor_cuit))
        if productor is None:
            raise LookupError("Productor no registrado")

        if not productor.verificacion_al_dia(datetime.now(UTC).date()):
            await self._outbox.publicar(
                EventoDeDominio(
                    nombre=RECEPCION_PRODUCTOR_SIN_VERIFICACION,
                    modulo_origen="composicion",
                    payload={"cuit": datos.productor_cuit},
                )
            )
        return await self._abrir(datos)
