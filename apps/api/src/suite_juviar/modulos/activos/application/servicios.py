"""Alta de activos, traslados entre sectores y reparaciones en talleres externos."""

from __future__ import annotations

import re
from dataclasses import asdict, replace
from datetime import UTC, datetime
from threading import RLock
from typing import Any
from uuid import uuid4

from ..domain.modelos import (
    BODEGAS,
    EMPRESAS,
    Activo,
    EstadoActivo,
    Movimiento,
    Reparacion,
    Sector,
    TipoActivo,
    TipoMovimiento,
)
from ..domain.puertos import RepositorioActivos


def _ahora() -> datetime:
    return datetime.now(UTC)


def _mismo_nombre(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold()


class GestionarActivos:
    def __init__(self, repo: RepositorioActivos) -> None:
        self.repo = repo
        # Una sola escritura a la vez: el correlativo no se repite y no se borra un tipo o sector en uso.
        self._bloqueo = RLock()

    # --- Tipos de activo -------------------------------------------------
    def guardar_tipo(self, nombre: str, prefijo: str, tipo_id: str | None = None) -> TipoActivo:
        prefijo = prefijo.strip().upper()
        with self._bloqueo:
            for otro in self.repo.tipos.values():
                if otro.id == tipo_id:
                    continue
                if _mismo_nombre(otro.nombre, nombre):
                    raise ValueError("Ya existe un tipo con ese nombre.")
                if otro.prefijo == prefijo:
                    raise ValueError(f"El prefijo {prefijo} ya lo usa «{otro.nombre}».")
            if tipo_id:
                actual = self._tipo(tipo_id)
                if actual.prefijo != prefijo and self._usado_por_tipo(tipo_id):
                    raise ValueError("No se puede cambiar el prefijo: ya hay etiquetas impresas con él.")
            tipo = TipoActivo(tipo_id or str(uuid4()), nombre.strip(), prefijo)
            self.repo.tipos[tipo.id] = tipo
        return tipo

    def eliminar_tipo(self, tipo_id: str) -> None:
        with self._bloqueo:
            self._tipo(tipo_id)
            if self._usado_por_tipo(tipo_id):
                raise ValueError("No se puede eliminar: hay activos cargados de este tipo.")
            del self.repo.tipos[tipo_id]

    def _usado_por_tipo(self, tipo_id: str) -> bool:
        return any(a.tipo_id == tipo_id for a in self.repo.activos.values())

    def _tipo(self, tipo_id: str) -> TipoActivo:
        try:
            return self.repo.tipos[tipo_id]
        except KeyError:
            raise LookupError("Tipo de activo inexistente.") from None

    # --- Sectores --------------------------------------------------------
    def guardar_sector(self, nombre: str, bodega: str, sector_id: str | None = None) -> Sector:
        with self._bloqueo:
            if any(s.id != sector_id and s.bodega == bodega and _mismo_nombre(s.nombre, nombre)
                   for s in self.repo.sectores.values()):
                raise ValueError("Esa bodega ya tiene un sector con ese nombre.")
            if sector_id:
                actual = self._sector(sector_id)
                if actual.bodega != bodega and any(a.sector_id == sector_id for a in self.repo.activos.values()):
                    raise ValueError("No se puede cambiar la bodega: hay equipos en este sector. Trasladalos primero.")
            sector = Sector(sector_id or str(uuid4()), nombre.strip(), bodega)
            self.repo.sectores[sector.id] = sector
            return sector

    def eliminar_sector(self, sector_id: str) -> None:
        with self._bloqueo:
            self._sector(sector_id)
            if any(a.sector_id == sector_id for a in self.repo.activos.values()):
                raise ValueError("No se puede eliminar: hay activos ubicados en este sector.")
            del self.repo.sectores[sector_id]

    def _sector(self, sector_id: str) -> Sector:
        try:
            return self.repo.sectores[sector_id]
        except KeyError:
            raise LookupError("Sector inexistente.") from None

    # --- Activos ---------------------------------------------------------
    def dar_de_alta(self, tipo_id: str, descripcion: str, sector_id: str, actor: str,
                    marca: str = "", modelo: str = "", numero_serie: str = "") -> Activo:
        tipo = self._tipo(tipo_id)
        self._sector(sector_id)
        with self._bloqueo:
            patron = re.compile(rf"^{tipo.prefijo}-(\d+)$")
            usados = [int(m.group(1)) for c in self.repo.activos if (m := patron.match(c))]
            codigo = f"{tipo.prefijo}-{max(usados, default=0) + 1:04d}"
            activo = Activo(codigo, tipo_id, descripcion.strip(), sector_id, marca.strip(),
                            modelo.strip(), numero_serie.strip(), EstadoActivo.EN_PLANTA, _ahora(), actor)
            self.repo.activos[codigo] = activo
        self.repo.registrar_movimiento(Movimiento(codigo, TipoMovimiento.ALTA, activo.alta_en, actor,
                                                  hacia_sector_id=sector_id))
        return activo

    def editar(self, codigo: str, descripcion: str, marca: str = "", modelo: str = "",
               numero_serie: str = "") -> Activo:
        with self._bloqueo:
            self._no_de_baja(self.obtener(codigo))
            activo = replace(self.obtener(codigo), descripcion=descripcion.strip(), marca=marca.strip(),
                             modelo=modelo.strip(), numero_serie=numero_serie.strip())
            self.repo.activos[codigo] = activo
            return activo

    def obtener(self, codigo: str) -> Activo:
        try:
            return self.repo.activos[codigo.strip().upper()]
        except KeyError:
            raise LookupError(f"No hay ningún activo con el código {codigo.strip().upper()}.") from None

    def trasladar(self, codigo: str, hacia_sector_id: str, actor: str, detalle: str = "") -> Activo:
        with self._bloqueo:
            activo = self.obtener(codigo)
            self._sector(hacia_sector_id)
            self._no_de_baja(activo)
            if activo.estado is EstadoActivo.EN_TALLER:
                raise ValueError("El equipo está en un taller externo; primero registrá su regreso.")
            if activo.sector_id == hacia_sector_id:
                raise ValueError("El equipo ya está en ese sector.")
            self.repo.activos[activo.codigo] = replace(activo, sector_id=hacia_sector_id)
            self.repo.registrar_movimiento(Movimiento(activo.codigo, TipoMovimiento.TRASLADO, _ahora(), actor,
                                                      activo.sector_id, hacia_sector_id, detalle.strip()))
            return self.repo.activos[activo.codigo]

    def enviar_a_taller(self, codigo: str, taller: str, motivo: str, actor: str) -> Reparacion:
        with self._bloqueo:
            activo = self.obtener(codigo)
            self._no_de_baja(activo)
            if activo.estado is EstadoActivo.EN_TALLER:
                raise ValueError("El equipo ya figura en un taller externo.")
            reparacion = Reparacion(str(uuid4()), activo.codigo, taller.strip(), motivo.strip(), _ahora(), actor)
            self.repo.reparaciones[reparacion.id] = reparacion
            self.repo.activos[activo.codigo] = replace(activo, estado=EstadoActivo.EN_TALLER)
            self.repo.registrar_movimiento(Movimiento(activo.codigo, TipoMovimiento.SALIDA_TALLER, reparacion.salida_en,
                                                      actor, activo.sector_id, None,
                                                      f"{reparacion.taller}: {reparacion.motivo}"))
            return reparacion

    def registrar_regreso(self, codigo: str, costo: float, trabajo_realizado: str, hacia_sector_id: str,
                          actor: str, empresa: str) -> Reparacion:
        with self._bloqueo:
            activo = self.obtener(codigo)
            self._sector(hacia_sector_id)
            abierta = next((r for r in self.repo.reparaciones.values() if r.codigo == activo.codigo and r.abierta), None)
            if activo.estado is not EstadoActivo.EN_TALLER or abierta is None:
                raise ValueError("El equipo no figura en un taller externo.")
            cerrada = replace(abierta, regreso_en=_ahora(), regreso_por=actor, costo=costo,
                              trabajo_realizado=trabajo_realizado.strip(), empresa=empresa.strip().upper())
            self.repo.reparaciones[cerrada.id] = cerrada
            self.repo.activos[activo.codigo] = replace(activo, estado=EstadoActivo.EN_PLANTA, sector_id=hacia_sector_id)
            self.repo.registrar_movimiento(Movimiento(activo.codigo, TipoMovimiento.REGRESO_TALLER, cerrada.regreso_en,
                                                      actor, None, hacia_sector_id, cerrada.trabajo_realizado))
            return cerrada

    def dar_de_baja(self, codigo: str, motivo: str, actor: str) -> Activo:
        if not motivo.strip():
            raise ValueError("Indicá el motivo de la baja.")
        with self._bloqueo:
            activo = self.obtener(codigo)
            self._no_de_baja(activo)
            if activo.estado is EstadoActivo.EN_TALLER:
                raise ValueError("El equipo está en un taller externo; primero registrá su regreso.")
            baja = replace(activo, estado=EstadoActivo.DE_BAJA, baja_motivo=motivo.strip(), baja_en=_ahora(),
                           baja_por=actor)
            self.repo.activos[activo.codigo] = baja
            self.repo.registrar_movimiento(Movimiento(activo.codigo, TipoMovimiento.BAJA, baja.baja_en, actor,
                                                      activo.sector_id, None, baja.baja_motivo))
            return baja

    @staticmethod
    def _no_de_baja(activo: Activo) -> None:
        if activo.estado is EstadoActivo.DE_BAJA:
            raise ValueError("El equipo está dado de baja.")

    # --- Consultas -------------------------------------------------------
    def _reparaciones_de(self, codigo: str) -> list[Reparacion]:
        return sorted((r for r in self.repo.reparaciones.values() if r.codigo == codigo),
                      key=lambda r: r.salida_en, reverse=True)

    def vista(self, activo: Activo) -> dict[str, Any]:
        tipo = self.repo.tipos.get(activo.tipo_id)
        sector = self.repo.sectores.get(activo.sector_id)
        reparaciones = self._reparaciones_de(activo.codigo)
        return {
            **asdict(activo),
            "tipo": tipo.nombre if tipo else "",
            "sector": sector.nombre if sector else "",
            "bodega": sector.bodega if sector else "",
            "bodega_nombre": BODEGAS.get(sector.bodega, "") if sector else "",
            "reparaciones": len(reparaciones),
            "costo_reparaciones": sum(r.costo or 0 for r in reparaciones),
            # Gasto en reparaciones según la empresa a la que fue cada factura.
            "costo_por_empresa": {e: sum(r.costo or 0 for r in reparaciones if r.empresa == e) for e in EMPRESAS},
        }

    def listar(self, tipo_id: str | None = None, sector_id: str | None = None,
               texto: str | None = None, mas_reparados: bool = False,
               bodega: str | None = None) -> list[dict[str, Any]]:
        buscado = (texto or "").strip().casefold()
        filas = []
        for activo in self.repo.activos.values():
            if tipo_id and activo.tipo_id != tipo_id:
                continue
            if sector_id and activo.sector_id != sector_id:
                continue
            fila = self.vista(activo)
            if bodega and fila["bodega"] != bodega:
                continue
            if buscado and buscado not in " ".join(
                str(fila[c]) for c in ("codigo", "descripcion", "marca", "modelo", "numero_serie", "tipo", "sector", "bodega_nombre")
            ).casefold():
                continue
            filas.append(fila)
        filas.sort(key=lambda f: f["codigo"])
        if mas_reparados:  # los equipos que más vuelven al taller, para decidir si conviene reemplazarlos
            filas.sort(key=lambda f: (f["reparaciones"], f["costo_reparaciones"]), reverse=True)
        return filas

    def ficha(self, codigo: str) -> dict[str, Any]:
        activo = self.obtener(codigo)
        nombres = {s.id: f"{s.nombre} ({BODEGAS[s.bodega]})" for s in self.repo.sectores.values()}
        historial = [
            {**asdict(m), "desde_sector": nombres.get(m.desde_sector_id or "", ""),
             "hacia_sector": nombres.get(m.hacia_sector_id or "", "")}
            for m in self.repo.movimientos() if m.codigo == activo.codigo
        ]
        return {
            **self.vista(activo),
            "historial": sorted(historial, key=lambda m: m["fecha"], reverse=True),
            "detalle_reparaciones": [asdict(r) for r in self._reparaciones_de(activo.codigo)],
        }
