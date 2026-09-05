"""Casos de uso de recepción. Dependen de puertos, nunca de adaptadores."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from suite_juviar.modulos.recepcion.domain.entidades import (
    OrigenPeso,
    Pesada,
    Romaneo,
)
from suite_juviar.modulos.recepcion.domain.eventos import (
    RECEPCION_ROMANEO_ABIERTO,
    RECEPCION_ROMANEO_CERRADO,
)
from suite_juviar.modulos.recepcion.domain.puertos import RepositorioRomaneos
from suite_juviar.plataforma.bitacora.domain.entidades import Actor, AsientoBitacora, TipoActor
from suite_juviar.plataforma.bitacora.domain.puertos import Bitacora
from suite_juviar.plataforma.outbox.domain.entidades import EventoDeDominio
from suite_juviar.plataforma.outbox.domain.puertos import Outbox


@dataclass(frozen=True, slots=True)
class DatosIngreso:
    productor_cuit: str
    transportista_cuit: str
    chofer_dni: str
    patente_chasis: str
    patente_acoplado: str | None
    variedad: str
    finca: str | None
    bruto_kg: Decimal
    origen_peso: OrigenPeso
    operador_legajo: str


class AbrirRomaneo:
    def __init__(
        self, romaneos: RepositorioRomaneos, outbox: Outbox, bitacora: Bitacora
    ) -> None:
        self._romaneos = romaneos
        self._outbox = outbox
        self._bitacora = bitacora

    async def __call__(self, datos: DatosIngreso) -> Romaneo:
        romaneo = Romaneo(
            numero=await self._romaneos.proximo_numero(),
            productor_cuit=datos.productor_cuit,
            transportista_cuit=datos.transportista_cuit,
            chofer_dni=datos.chofer_dni,
            patente_chasis=datos.patente_chasis,
            patente_acoplado=datos.patente_acoplado,
            variedad=datos.variedad,
            finca=datos.finca,
            bruto=Pesada(
                kg=datos.bruto_kg,
                origen=datos.origen_peso,
                registrada_en=datetime.now(UTC),
                operador_legajo=datos.operador_legajo,
            ),
        )
        # Todo dentro de la misma transacción: estado, evento y bitácora.
        await self._romaneos.guardar(romaneo)
        await self._outbox.publicar(
            EventoDeDominio(
                nombre=RECEPCION_ROMANEO_ABIERTO,
                modulo_origen="recepcion",
                payload={
                    "romaneo_id": str(romaneo.id),
                    "numero": romaneo.numero,
                    "productor_cuit": romaneo.productor_cuit,
                    "variedad": romaneo.variedad,
                },
            )
        )
        await self._bitacora.registrar(
            AsientoBitacora(
                accion="recepcion.romaneo.abierto",
                actor=Actor(TipoActor.EMPLEADO, datos.operador_legajo),
                entidad="romaneo",
                entidad_id=str(romaneo.id),
                modulo="recepcion",
                datos={"bruto_kg": str(datos.bruto_kg), "origen": datos.origen_peso},
            )
        )
        return romaneo


class CerrarRomaneo:
    def __init__(
        self, romaneos: RepositorioRomaneos, outbox: Outbox, bitacora: Bitacora
    ) -> None:
        self._romaneos = romaneos
        self._outbox = outbox
        self._bitacora = bitacora

    async def __call__(
        self, romaneo_id: UUID, tara_kg: Decimal, origen: OrigenPeso, operador: str
    ) -> Romaneo:
        romaneo = await self._romaneos.obtener(romaneo_id)
        if romaneo is None:
            raise LookupError("Romaneo inexistente")
        romaneo.cerrar(
            Pesada(
                kg=tara_kg,
                origen=origen,
                registrada_en=datetime.now(UTC),
                operador_legajo=operador,
            )
        )
        await self._romaneos.guardar(romaneo)
        await self._outbox.publicar(
            EventoDeDominio(
                nombre=RECEPCION_ROMANEO_CERRADO,
                modulo_origen="recepcion",
                payload={
                    "romaneo_id": str(romaneo.id),
                    "numero": romaneo.numero,
                    "productor_cuit": romaneo.productor_cuit,
                    "variedad": romaneo.variedad,
                    "neto_kg": str(romaneo.neto_kg),
                },
            )
        )
        await self._bitacora.registrar(
            AsientoBitacora(
                accion="recepcion.romaneo.cerrado",
                actor=Actor(TipoActor.EMPLEADO, operador),
                entidad="romaneo",
                entidad_id=str(romaneo.id),
                modulo="recepcion",
                datos={"neto_kg": str(romaneo.neto_kg)},
            )
        )
        return romaneo
