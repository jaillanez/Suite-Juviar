"""Remitos de salida: carga, firma del Encargado, salida por guardia y control del regreso."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any
from uuid import uuid4

from ..domain.modelos import BODEGAS, EstadoActivo
from ..domain.puertos import PuertaGuardia, RepositorioRemitos
from ..domain.remitos import (
    EstadoRemito,
    Firma,
    ItemRemito,
    MensajeWhatsapp,
    ModoFirma,
    ModoWhatsapp,
    ParametrosRemitos,
    Remito,
)
from .servicios import GestionarActivos

_registro = logging.getLogger(__name__)
_CODIGO = re.compile(r"\b([A-Z]{2,5}-\d{1,6})\b")
_ABIERTOS = {EstadoRemito.BORRADOR, EstadoRemito.AUTORIZADO, EstadoRemito.AFUERA}


def _ahora() -> datetime:
    return datetime.now(UTC)


class GestionarRemitos:
    def __init__(self, repo: RepositorioRemitos, activos: GestionarActivos, puerta: PuertaGuardia,
                 reloj: Callable[[], datetime] = _ahora) -> None:
        self.repo = repo
        self.activos = activos
        self.puerta = puerta
        self._reloj = reloj
        self._bloqueo = RLock()

    # --- Parámetros ------------------------------------------------------
    def parametros(self) -> ParametrosRemitos:
        return self.repo.parametros.get("remitos") or ParametrosRemitos()

    def guardar_parametros(self, dias_maximos_fuera: int | None, modo_whatsapp: str, actor: str) -> ParametrosRemitos:
        try:
            modo = ModoWhatsapp(modo_whatsapp)
        except ValueError:
            raise ValueError("Elegí cómo entra lo que llega por WhatsApp.") from None
        nuevos = ParametrosRemitos(dias_maximos_fuera, modo, actor, self._reloj())
        self.repo.parametros["remitos"] = nuevos
        return nuevos

    # --- Carga -----------------------------------------------------------
    def obtener(self, remito_id: str) -> Remito:
        try:
            return self.repo.remitos[remito_id]
        except KeyError:
            raise LookupError("No existe ese remito.") from None

    def _items(self, items: list[dict[str, Any]], remito_id: str | None) -> tuple[ItemRemito, ...]:
        armados = []
        for item in items:
            codigo = (item.get("codigo") or "").strip().upper() or None
            descripcion = (item.get("descripcion") or "").strip()
            if codigo:
                activo = self.activos.obtener(codigo)
                if activo.estado is EstadoActivo.DE_BAJA:
                    raise ValueError(f"{codigo} está dado de baja.")
                if activo.estado is EstadoActivo.EN_TALLER:
                    raise ValueError(f"{codigo} ya figura en un taller externo.")
                otro = self._remito_abierto_con(codigo, remito_id)
                if otro:
                    raise ValueError(f"{codigo} ya está en el remito N.º {otro.numero}.")
                descripcion = descripcion or activo.descripcion
            armados.append(ItemRemito(descripcion[:200], codigo, int(item.get("cantidad") or 1)))
        return tuple(armados)

    def _remito_abierto_con(self, codigo: str, salvo: str | None) -> Remito | None:
        return next((r for r in self.repo.remitos.values()
                     if r.id != salvo and r.estado in _ABIERTOS and any(i.codigo == codigo and i.afuera for i in r.items)),
                    None)

    def crear(self, bodega: str, destino: str, motivo: str, items: list[dict[str, Any]], actor: str,
              origen: str = "gestion", foto: bytes | None = None, foto_tipo: str = "") -> Remito:
        with self._bloqueo:
            numero = max((r.numero for r in self.repo.remitos.values()), default=0) + 1
            remito = Remito(str(uuid4()), numero, bodega.strip(), destino.strip()[:120], motivo.strip()[:300],
                            self._items(items, None), actor, self._reloj(), origen, foto, foto_tipo)
            self.repo.remitos[remito.id] = remito
            return remito

    def editar(self, remito_id: str, bodega: str, destino: str, motivo: str, items: list[dict[str, Any]]) -> Remito:
        with self._bloqueo:
            remito = self.obtener(remito_id)
            if remito.estado is not EstadoRemito.BORRADOR:
                raise ValueError("Sólo se puede cambiar un remito que todavía no se firmó.")
            nuevo = replace(remito, bodega=bodega.strip(), destino=destino.strip()[:120], motivo=motivo.strip()[:300],
                            items=self._items(items, remito.id))
            self.repo.remitos[remito.id] = nuevo
            return nuevo

    # --- Firma, anulación y salida ----------------------------------------
    def firmar(self, remito_id: str, modo: str, imagen: bytes | None, actor: str) -> Remito:
        with self._bloqueo:
            remito = self.obtener(remito_id)
            if remito.estado is not EstadoRemito.BORRADOR:
                raise ValueError("Ese remito ya está firmado o anulado.")
            try:
                modo_firma = ModoFirma(modo)
            except ValueError:
                raise ValueError("Elegí si firmás en el celular o en papel.") from None
            # Se vuelve a controlar: un equipo pudo haber salido por otro camino desde que se cargó.
            self._items([asdict(i) for i in remito.items], remito.id)
            firmado = replace(remito, firma=Firma(modo_firma, actor, self._reloj(),
                                                   imagen if modo_firma is ModoFirma.CELULAR else None))
            # Sin la guardia enterada no sirve: si la base de la fila no responde, no queda firmado.
            try:
                self.puerta.publicar(firmado)
            except Exception as exc:
                _registro.exception("No se pudo publicar el remito %s a la guardia.", remito.numero)
                raise ValueError("No se pudo avisar a la guardia. Probá de nuevo en unos minutos.") from exc
            self.repo.remitos[remito.id] = firmado
            return firmado

    def anular(self, remito_id: str, motivo: str, actor: str) -> Remito:
        if not motivo.strip():
            raise ValueError("Indicá por qué se anula.")
        with self._bloqueo:
            self.sincronizar()
            remito = self.obtener(remito_id)
            if remito.estado not in {EstadoRemito.BORRADOR, EstadoRemito.AUTORIZADO}:
                raise ValueError("Ese remito ya salió de la planta o está anulado; no se puede anular.")
            if remito.estado is EstadoRemito.AUTORIZADO:
                try:
                    self.puerta.anular(remito.id, actor)
                except ValueError:
                    raise
                except Exception as exc:
                    _registro.exception("No se pudo anular el remito %s en la guardia.", remito.numero)
                    raise ValueError("No se pudo avisar a la guardia. Probá de nuevo en unos minutos.") from exc
            anulado = replace(remito, anulado_en=self._reloj(), anulado_por=actor, anulado_motivo=motivo.strip()[:300])
            self.repo.remitos[remito.id] = anulado
            return anulado

    def sincronizar(self) -> int:
        """Trae de la base de la fila las salidas que marcó la guardia y lo que llegó por WhatsApp."""
        with self._bloqueo:
            esperando = [r.id for r in self.repo.remitos.values() if r.estado is EstadoRemito.AUTORIZADO]
            salidas = self.puerta.salidas(esperando) if esperando else {}
            for remito_id, salida in salidas.items():
                remito = self.repo.remitos.get(remito_id)
                if remito is None or remito.estado is not EstadoRemito.AUTORIZADO:
                    continue
                self.repo.remitos[remito_id] = replace(remito, salio_en=salida.salio_en, salio_por=salida.salio_por)
                for item in remito.items:
                    if not item.codigo:
                        continue
                    try:
                        self.activos.enviar_a_taller(item.codigo, remito.destino,
                                                     f"Remito N.º {remito.numero}: {remito.motivo}", salida.salio_por)
                    except (ValueError, LookupError):
                        _registro.warning("El equipo %s del remito %s no se pudo pasar a taller.",
                                          item.codigo, remito.numero)
            self._recibir_mensajes()
            return len(salidas)

    # --- Regreso ---------------------------------------------------------
    def marcar_regreso(self, remito_id: str, indice: int, actor: str) -> Remito:
        """Herramienta sin código que volvió. Los equipos con código vuelven por su ficha."""
        with self._bloqueo:
            remito = self.obtener(remito_id)
            if remito.estado is not EstadoRemito.AFUERA:
                raise ValueError("Ese remito no tiene cosas afuera.")
            if not 0 <= indice < len(remito.items):
                raise LookupError("Ese ítem no está en el remito.")
            item = remito.items[indice]
            if item.codigo:
                raise ValueError(f"{item.codigo} vuelve registrando el regreso del taller, con su costo.")
            if not item.afuera:
                raise ValueError("Ese ítem ya volvió.")
            items = list(remito.items)
            items[indice] = replace(item, volvio_en=self._reloj(), volvio_por=actor)
            nuevo = replace(remito, items=tuple(items))
            self.repo.remitos[remito.id] = nuevo
            return nuevo

    def regreso_equipo(self, remito_id: str, codigo: str, costo: float, trabajo: str, sector_id: str,
                       empresa: str, actor: str) -> Remito:
        with self._bloqueo:
            remito = self.obtener(remito_id)
            codigo = codigo.strip().upper()
            if remito.estado is not EstadoRemito.AFUERA or not any(i.codigo == codigo and i.afuera for i in remito.items):
                raise ValueError(f"{codigo} no figura afuera en este remito.")
            self.activos.registrar_regreso(codigo, costo, trabajo, sector_id, actor, empresa)
            return self._conciliar(remito)

    def _conciliar(self, remito: Remito) -> Remito:
        """Un equipo cuyo regreso se cargó desde su ficha también vuelve en el remito."""
        if remito.estado is not EstadoRemito.AFUERA or remito.salio_en is None:
            return remito
        items, cambio = list(remito.items), False
        for n, item in enumerate(items):
            if not item.codigo or not item.afuera:
                continue
            vuelta = next((r for r in self.activos.repo.reparaciones.values()
                           if r.codigo == item.codigo and r.regreso_en and r.salida_en >= remito.salio_en), None)
            if vuelta:
                items[n] = replace(item, volvio_en=vuelta.regreso_en, volvio_por=vuelta.regreso_por or "")
                cambio = True
        if not cambio:
            return remito
        nuevo = replace(remito, items=tuple(items))
        self.repo.remitos[remito.id] = nuevo
        return nuevo

    # --- WhatsApp --------------------------------------------------------
    def _recibir_mensajes(self) -> None:
        recibidos = self.puerta.tomar_mensajes()
        if not recibidos:
            return
        modo = self.parametros().modo_whatsapp
        for entrante in recibidos:
            if entrante.id in self.repo.mensajes:
                continue
            mensaje = MensajeWhatsapp(entrante.id, entrante.telefono, entrante.nombre, entrante.texto[:1000],
                                      entrante.recibido_en, entrante.foto, entrante.foto_tipo)
            if modo is ModoWhatsapp.DIRECTO:
                remito = self._remito_desde(mensaje, f"whatsapp:{mensaje.nombre}")
                mensaje = replace(mensaje, remito_id=remito.id)
            self.repo.mensajes[mensaje.id] = mensaje
        self.puerta.confirmar_mensajes([m.id for m in recibidos])

    def _remito_desde(self, mensaje: MensajeWhatsapp, actor: str) -> Remito:
        texto = mensaje.texto.strip()
        items: list[dict[str, Any]] = []
        for codigo in dict.fromkeys(_CODIGO.findall(texto.upper())):
            try:
                self._items([{"codigo": codigo}], None)
            except (ValueError, LookupError):
                continue
            items.append({"codigo": codigo})
        if not items:
            items = [{"descripcion": texto[:200] or "Ver la foto"}]
        bodega = next((clave for clave, nombre in BODEGAS.items() if nombre.casefold() in texto.casefold()), "")
        return self.crear(bodega, "", texto[:300], items, actor, "whatsapp", mensaje.foto, mensaje.foto_tipo)

    def mensajes(self) -> list[dict[str, Any]]:
        return [self._vista_mensaje(m) for m in sorted(self.repo.mensajes.values(), key=lambda m: m.recibido_en,
                                                       reverse=True)]

    def _vista_mensaje(self, m: MensajeWhatsapp) -> dict[str, Any]:
        remito = self.repo.remitos.get(m.remito_id or "")
        return {"id": m.id, "nombre": m.nombre, "texto": m.texto, "recibido_en": m.recibido_en,
                "con_foto": m.foto is not None, "remito_id": m.remito_id,
                "remito_numero": remito.numero if remito else None,
                "descartado": bool(m.descartado_por), "pendiente": not m.remito_id and not m.descartado_por}

    def obtener_mensaje(self, mensaje_id: str) -> MensajeWhatsapp:
        try:
            return self.repo.mensajes[mensaje_id]
        except KeyError:
            raise LookupError("No existe ese mensaje.") from None

    def armar_desde_mensaje(self, mensaje_id: str, actor: str) -> Remito:
        with self._bloqueo:
            mensaje = self.obtener_mensaje(mensaje_id)
            if mensaje.remito_id or mensaje.descartado_por:
                raise ValueError("Ese mensaje ya se usó o se descartó.")
            remito = self._remito_desde(mensaje, actor)
            self.repo.mensajes[mensaje.id] = replace(mensaje, remito_id=remito.id)
            return remito

    def descartar_mensaje(self, mensaje_id: str, actor: str) -> None:
        with self._bloqueo:
            mensaje = self.obtener_mensaje(mensaje_id)
            if mensaje.remito_id:
                raise ValueError("Ese mensaje ya tiene un remito.")
            self.repo.mensajes[mensaje.id] = replace(mensaje, descartado_por=actor)

    # --- Consultas -------------------------------------------------------
    def vista(self, remito: Remito) -> dict[str, Any]:
        remito = self._conciliar(remito)
        limite = self.parametros().dias_maximos_fuera
        demorado = bool(limite and remito.estado is EstadoRemito.AFUERA and remito.salio_en
                        and self._reloj() - remito.salio_en > timedelta(days=limite))
        return {
            "id": remito.id, "numero": remito.numero, "bodega": remito.bodega,
            "bodega_nombre": BODEGAS.get(remito.bodega, ""), "destino": remito.destino, "motivo": remito.motivo,
            "items": [asdict(i) for i in remito.items], "estado": remito.estado.value,
            "creado_por": remito.creado_por, "creado_en": remito.creado_en, "origen": remito.origen,
            "con_foto": remito.foto is not None,
            "firma": ({"modo": remito.firma.modo.value, "por": remito.firma.por, "en": remito.firma.en}
                      if remito.firma else None),
            "salio_en": remito.salio_en, "salio_por": remito.salio_por,
            "anulado_en": remito.anulado_en, "anulado_por": remito.anulado_por, "anulado_motivo": remito.anulado_motivo,
            "afuera": sum(1 for i in remito.items if i.afuera) if remito.salio_en else 0,
            "dias_afuera": (self._reloj() - remito.salio_en).days if remito.salio_en else None,
            "demorado": demorado,
        }

    def listar(self, estado: str | None = None) -> list[dict[str, Any]]:
        filas = [self.vista(r) for r in self.repo.remitos.values()]
        if estado:
            filas = [f for f in filas if f["estado"] == estado]
        return sorted(filas, key=lambda f: (not f["demorado"], -f["numero"]))
