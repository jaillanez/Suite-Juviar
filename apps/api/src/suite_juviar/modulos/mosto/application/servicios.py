"""Compras de mosto, análisis, aprobaciones, viajes, liquidación y alarma de mosto virgen."""

from __future__ import annotations

import logging
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any
from uuid import uuid4

from ..domain.modelos import (
    BODEGAS,
    TIPOS,
    Analisis,
    Aviso,
    Compra,
    Decision,
    Destinatario,
    Envio,
    EstadoCompra,
    Etapa,
    MuestraPileta,
    Parametros,
    Paso,
    Viaje,
    liquidar,
)
from ..domain.puertos import Notificador, RepositorioMosto

_registro = logging.getLogger(__name__)
PARAMETROS = "mosto"
ESTADOS = {
    EstadoCompra.EN_ANALISIS: "En análisis",
    EstadoCompra.RECHAZADA_CALIDAD: "Rechazada por Calidad",
    EstadoCompra.APROBADA: "Aprobada",
    EstadoCompra.RECHAZADA: "Rechazada",
    EstadoCompra.CERRADA: "Cerrada",
}


def _ahora() -> datetime:
    return datetime.now(UTC)


def _motivo(motivo: str) -> str:
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("Escribí el motivo.")
    return motivo[:300]


class GestionarMosto:
    def __init__(self, repo: RepositorioMosto, notificadores: tuple[Notificador, ...] = (),
                 reloj=_ahora) -> None:
        self.repo = repo
        self.notificadores = notificadores
        self._reloj = reloj
        self._bloqueo = RLock()

    # --- Parámetros ------------------------------------------------------
    def parametros(self) -> Parametros:
        return self.repo.parametros.get(PARAMETROS) or Parametros()

    def guardar_parametros(self, azucar_referencia: float, margen_gl: float, horas_virgen: float | None,
                           destinatarios: list[dict[str, str]], actor: str) -> Parametros:
        lista = tuple(Destinatario(d.get("nombre", "").strip(), d.get("correo", "").strip(),
                                   d.get("telefono", "").strip()) for d in destinatarios)
        nuevos = Parametros(azucar_referencia, margen_gl, horas_virgen, lista, actor, self._reloj())
        self.repo.parametros[PARAMETROS] = nuevos
        return nuevos

    # --- Compras ---------------------------------------------------------
    def obtener(self, compra_id: str) -> Compra:
        compra = self.repo.compras.get(compra_id)
        if compra is None:
            raise LookupError("No existe esa compra.")
        return compra

    def crear_compra(self, proveedor: str, cuit: str, tipo: str, litros: float, precio_base: float,
                     actor: str) -> Compra:
        with self._bloqueo:
            numero = max((c.numero for c in self.repo.compras.values()), default=0) + 1
            compra = Compra(uuid4().hex, numero, proveedor.strip(), cuit.strip(), tipo, litros, precio_base,
                            actor, self._reloj())
            self.repo.compras[compra.id] = compra
        return compra

    def _cambiar(self, compra_id: str, cambio) -> Compra:
        with self._bloqueo:
            nueva = cambio(self.obtener(compra_id))
            self.repo.compras[nueva.id] = nueva
        return nueva

    def cargar_analisis_oferta(self, compra_id: str, datos: dict[str, Any], actor: str) -> Compra:
        def cambio(c: Compra) -> Compra:
            if c.estado is not EstadoCompra.EN_ANALISIS:
                raise ValueError("La oferta ya tiene decisión de Calidad: no se cambia su análisis.")
            return replace(c, analisis=Analisis(actor=actor, fecha=self._reloj(), **datos))
        return self._cambiar(compra_id, cambio)

    def decidir(self, compra_id: str, etapa: Etapa, aprueba: bool, motivo: str, actor: str) -> Compra:
        def cambio(c: Compra) -> Compra:
            estado = c.estado
            if etapa is Etapa.CALIDAD:
                if estado is not EstadoCompra.EN_ANALISIS:
                    raise ValueError("Calidad ya decidió sobre esta oferta.")
                if c.analisis is None:
                    raise ValueError("Primero cargá el análisis de la muestra.")
                texto = (motivo or "").strip()[:300] if aprueba else _motivo(motivo)
            elif etapa is Etapa.PRODUCCION:
                if estado is not EstadoCompra.RECHAZADA_CALIDAD:
                    raise ValueError("El Jefe de Producción decide sólo sobre ofertas que rechazó Calidad.")
                texto = _motivo(motivo)
            else:
                if estado not in {EstadoCompra.RECHAZADA_CALIDAD, EstadoCompra.RECHAZADA}:
                    raise ValueError("Comercial decide sólo sobre ofertas rechazadas.")
                texto = _motivo(motivo)
            return replace(c, decisiones=(*c.decisiones, Decision(etapa, aprueba, texto, actor, self._reloj())))
        return self._cambiar(compra_id, cambio)

    def agregar_pileta(self, compra_id: str, pileta: str, litros: float, datos: dict[str, Any],
                       actor: str) -> Compra:
        def cambio(c: Compra) -> Compra:
            if c.estado is not EstadoCompra.APROBADA:
                raise ValueError("Las piletas se ratifican con la oferta aprobada.")
            muestra = MuestraPileta(uuid4().hex, pileta.strip(), litros,
                                    Analisis(actor=actor, fecha=self._reloj(), **datos))
            return replace(c, piletas=(*c.piletas, muestra))
        return self._cambiar(compra_id, cambio)

    def excepcion_margen(self, compra_id: str, sin_margen: bool, motivo: str) -> Compra:
        def cambio(c: Compra) -> Compra:
            if c.estado is EstadoCompra.CERRADA:
                raise ValueError("La compra está cerrada.")
            return replace(c, sin_margen=sin_margen, sin_margen_motivo=_motivo(motivo) if sin_margen else "")
        return self._cambiar(compra_id, cambio)

    def viajes_de(self, compra_id: str) -> list[Viaje]:
        return sorted((v for v in self.repo.viajes.values() if v.compra_id == compra_id),
                      key=lambda v: v.ingreso_en)

    def cerrar(self, compra_id: str, actor: str) -> Compra:
        def cambio(c: Compra) -> Compra:
            if c.estado is not EstadoCompra.APROBADA:
                raise ValueError("Sólo se cierra una compra aprobada.")
            viajes = self.viajes_de(c.id)
            if not viajes:
                raise ValueError("La compra no tiene viajes.")
            if any(v.analisis is None for v in viajes):
                raise ValueError("Hay viajes sin análisis de azúcar.")
            if any(v.descarga is None for v in viajes):
                raise ValueError("Hay viajes que todavía no se descargaron.")
            return replace(c, cerrada_en=self._reloj(), cerrada_por=actor,
                           liquidacion=liquidar(c, viajes, self.parametros()))
        return self._cambiar(compra_id, cambio)

    def vista(self, compra: Compra) -> dict[str, Any]:
        viajes = self.viajes_de(compra.id)
        liquidacion = compra.liquidacion
        if liquidacion is None and any(v.analisis for v in viajes):
            liquidacion = liquidar(compra, viajes, self.parametros())
        datos = asdict(compra)
        datos.update(
            estado=compra.estado.value, estado_nombre=ESTADOS[compra.estado], tipo_nombre=TIPOS[compra.tipo],
            litros_recibidos=sum(v.litros for v in viajes), viajes=len(viajes),
            liquidacion=asdict(liquidacion) if liquidacion else None,
            liquidacion_final=compra.liquidacion is not None,
        )
        return datos

    def listar(self) -> list[dict[str, Any]]:
        return [self.vista(c) for c in sorted(self.repo.compras.values(), key=lambda c: -c.numero)]

    def ficha(self, compra_id: str) -> dict[str, Any]:
        compra = self.obtener(compra_id)
        return {**self.vista(compra), "detalle_viajes": [self.vista_viaje(v) for v in self.viajes_de(compra.id)]}

    # --- Viajes ----------------------------------------------------------
    def obtener_viaje(self, viaje_id: str) -> Viaje:
        viaje = self.repo.viajes.get(viaje_id)
        if viaje is None:
            raise LookupError("No existe ese viaje.")
        return viaje

    def ingresar(self, compra_id: str, bodega: str, patente: str, litros: float, actor: str) -> Viaje:
        with self._bloqueo:
            compra = self.obtener(compra_id)
            if compra.estado is not EstadoCompra.APROBADA:
                raise ValueError("Sólo entran viajes de una compra aprobada y abierta.")
            patente = "".join(patente.split()).upper()
            if any(v.patente == patente and v.descarga is None for v in self.repo.viajes.values()):
                raise ValueError(f"El camión {patente} ya está en planta sin descargar.")
            viaje = Viaje(uuid4().hex, compra.id, bodega, patente, litros, actor, self._reloj())
            self.repo.viajes[viaje.id] = viaje
        return viaje

    def _cambiar_viaje(self, viaje_id: str, cambio) -> Viaje:
        with self._bloqueo:
            viaje = self.obtener_viaje(viaje_id)
            if self.obtener(viaje.compra_id).estado is EstadoCompra.CERRADA:
                raise ValueError("La compra de este viaje está cerrada.")
            nuevo = cambio(viaje)
            self.repo.viajes[nuevo.id] = nuevo
        return nuevo

    def analizar_viaje(self, viaje_id: str, datos: dict[str, Any], actor: str) -> Viaje:
        return self._cambiar_viaje(viaje_id, lambda v: replace(
            v, analisis=Analisis(actor=actor, fecha=self._reloj(), **datos)))

    def descargar(self, viaje_id: str, lugar: str, nota: str, actor: str) -> Viaje:
        def cambio(v: Viaje) -> Viaje:
            if v.descarga is not None:
                raise ValueError("El viaje ya está descargado.")
            if not lugar.strip():
                raise ValueError("Escribí dónde se descargó.")
            return replace(v, descarga=Paso(lugar.strip()[:80], actor, self._reloj(), nota.strip()[:200]))
        return self._cambiar_viaje(viaje_id, cambio)

    def mover(self, viaje_id: str, lugar: str, nota: str, actor: str) -> Viaje:
        def cambio(v: Viaje) -> Viaje:
            if v.descarga is None:
                raise ValueError("Primero registrá la descarga.")
            if not lugar.strip():
                raise ValueError("Escribí a dónde pasa el mosto.")
            return replace(v, recorrido=(*v.recorrido, Paso(lugar.strip()[:80], actor, self._reloj(),
                                                            nota.strip()[:200])))
        return self._cambiar_viaje(viaje_id, cambio)

    def demorado(self, viaje: Viaje, compra: Compra, ahora: datetime | None = None) -> bool:
        horas = self.parametros().horas_virgen
        return (compra.tipo == "virgen" and viaje.descarga is None and horas is not None
                and (ahora or self._reloj()) - viaje.ingreso_en >= timedelta(hours=horas))

    def vista_viaje(self, viaje: Viaje) -> dict[str, Any]:
        compra = self.obtener(viaje.compra_id)
        datos = asdict(viaje)
        datos.update(
            compra_numero=compra.numero, proveedor=compra.proveedor, tipo=compra.tipo,
            tipo_nombre=TIPOS[compra.tipo], bodega_nombre=BODEGAS[viaje.bodega],
            demorado=self.demorado(viaje, compra), compra_cerrada=compra.estado is EstadoCompra.CERRADA,
            horas_en_planta=round(((viaje.descarga.fecha if viaje.descarga else self._reloj())
                                   - viaje.ingreso_en).total_seconds() / 3600, 1),
        )
        return datos

    def listar_viajes(self, en_planta: bool = False) -> list[dict[str, Any]]:
        viajes = sorted(self.repo.viajes.values(), key=lambda v: v.ingreso_en, reverse=True)
        return [self.vista_viaje(v) for v in viajes if not en_planta or v.descarga is None]

    # --- Alarma de mosto virgen -------------------------------------------
    def revisar_demoras(self) -> list[Aviso]:
        """Avisa una vez por cada camión de mosto virgen que pasó el tiempo límite sin descargarse."""
        parametros = self.parametros()
        if parametros.horas_virgen is None:
            return []
        ahora = self._reloj()
        nuevos = []
        with self._bloqueo:
            for viaje in list(self.repo.viajes.values()):
                compra = self.repo.compras.get(viaje.compra_id)
                if compra is None or viaje.avisado_en is not None or not self.demorado(viaje, compra, ahora):
                    continue
                self.repo.viajes[viaje.id] = replace(viaje, avisado_en=ahora)
                horas = (ahora - viaje.ingreso_en).total_seconds() / 3600
                texto = (f"URGENTE mosto virgen: el camión {viaje.patente} ({compra.proveedor}, compra "
                         f"N.º {compra.numero}) lleva {horas:.1f} h en {BODEGAS[viaje.bodega]} sin descargarse. "
                         f"Hay que descargarlo o pasarlo al concentrador.")
                nuevos.append(Aviso(uuid4().hex, viaje.id, texto, ahora))
        for aviso in nuevos:
            envios = tuple(self._enviar(aviso.texto, parametros.destinatarios))
            self.repo.avisos[aviso.id] = replace(aviso, envios=envios)
        return [self.repo.avisos[a.id] for a in nuevos]

    def _enviar(self, texto: str, destinatarios: tuple[Destinatario, ...]):
        for notificador in self.notificadores:
            for d in destinatarios:
                destino = d.correo if notificador.canal == "correo" else d.telefono
                if not destino:
                    continue
                try:
                    resultado, detalle = notificador.enviar(destino, "Mosto virgen sin descargar", texto), ""
                except Exception as exc:  # noqa: BLE001 - un canal caído no frena a los demás
                    _registro.warning("Aviso de mosto por %s a %s no salió: %s", notificador.canal, d.nombre, exc)
                    resultado, detalle = "error", str(exc)[:200]
                yield Envio(notificador.canal, destino, d.nombre, resultado, detalle)

    def avisos(self) -> list[dict[str, Any]]:
        lista = sorted(self.repo.avisos.values(), key=lambda a: a.creado_en, reverse=True)[:50]
        return [{**asdict(a), "en_planta": (v := self.repo.viajes.get(a.viaje_id)) is not None and v.descarga is None}
                for a in lista]
