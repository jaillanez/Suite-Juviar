"""Bandeja de RRHH por WhatsApp, CV que llegan por WhatsApp y recorridos del micro del personal."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from threading import RLock
from typing import Any

from ..domain.modelos import (
    EXTENSIONES,
    CVEntrante,
    EstadoMensaje,
    MensajeRRHH,
    TipoMensaje,
)
from ..domain.puertos import PuertaDMZ, RepositorioBandeja

_registro = logging.getLogger(__name__)

# Lo que se le muestra a RRHH de la lectura del certificado (el diagnóstico queda para Salud).
CAMPOS_LECTURA = ("dias_detectados", "fecha_desde", "fecha_hasta", "fecha_reintegro", "profesional",
                  "resumen", "tipo_accidente", "paciente_nombre", "paciente_dni", "texto_detectado",
                  "motor", "mensaje")
SIN_LECTURA = "No pudimos leer los datos de tu certificado médico. RRHH lo va a revisar."


def _ahora() -> datetime:
    return datetime.now(UTC)


def _fecha(valor: Any) -> date | None:
    try:
        return date.fromisoformat(str(valor)[:10]) if valor else None
    except ValueError:
        return None


def _dias(valor: Any) -> int | None:
    try:
        dias = int(valor)
    except (TypeError, ValueError):
        return None
    return dias if 0 < dias <= 365 else None


def limpiar_lectura(lectura: dict[str, Any]) -> dict[str, Any]:
    datos = {clave: lectura.get(clave) for clave in CAMPOS_LECTURA if lectura.get(clave) not in (None, "")}
    if "dias_detectados" in datos:
        datos["dias_detectados"] = _dias(datos["dias_detectados"])
    for clave in ("fecha_desde", "fecha_hasta", "fecha_reintegro"):
        if clave in datos:
            fecha = _fecha(datos[clave])
            datos[clave] = fecha.isoformat() if fecha else None
    return {clave: valor for clave, valor in datos.items() if valor is not None}


def texto_confirmacion(lectura: dict[str, Any] | None) -> tuple[str, bool]:
    """Lo que se le manda al empleado: los días y las fechas que se leyeron, para que confirme.
    Sin ningún dato leído no se pide confirmación."""
    lectura = lectura or {}
    dias, desde, hasta = lectura.get("dias_detectados"), _fecha(lectura.get("fecha_desde")), _fecha(
        lectura.get("fecha_hasta"))
    if not (dias or desde or hasta):
        return SIN_LECTURA, False
    lineas = ["Leímos tu certificado médico:"]
    if dias:
        lineas.append(f"• Días: {dias}")
    if desde:
        lineas.append(f"• Desde: {desde:%d/%m/%Y}")
    if hasta:
        lineas.append(f"• Hasta: {hasta:%d/%m/%Y}")
    lineas += ["¿Es correcto? Respondé con el número:", "1 = Sí, es correcto", "2 = No"]
    return "\n".join(lineas), True


class BandejaRRHH:
    def __init__(
        self,
        repo: RepositorioBandeja,
        puerta: PuertaDMZ,
        leer_certificado: Callable[[str, bytes, str], dict[str, Any]],
        adjuntar_legajo: Callable[[str, str, bytes, str], str],
        incorporar_cv: Callable[[CVEntrante], bool],
        sedes: dict[str, str],
        reloj: Callable[[], datetime] = _ahora,
    ) -> None:
        self.repo = repo
        self.puerta = puerta
        self._leer = leer_certificado  # (nombre con extensión, contenido, legajo)
        self._adjuntar = adjuntar_legajo  # (legajo, nombre, contenido, actor) -> id del adjunto
        self._incorporar_cv = incorporar_cv
        self.sedes = sedes
        self._reloj = reloj
        self._bloqueo = RLock()

    # --- Sincronización con la DMZ -----------------------------------------
    def sincronizar(self) -> int:
        """Trae los mensajes y CV nuevos y las respuestas de los empleados. Devuelve los nuevos."""
        with self._bloqueo:
            nuevos = self._recibir_mensajes()
            self._avisar_pendientes()
            self._recibir_cvs()
            self._actualizar_confirmaciones()
            return nuevos

    def _recibir_mensajes(self) -> int:
        recibidos = self.puerta.tomar_mensajes()
        nuevos = 0
        for entrante in recibidos:
            if self.repo.obtener(entrante.id) is not None:
                continue
            try:
                tipo = TipoMensaje(entrante.tipo)
            except ValueError:
                _registro.warning("Mensaje de RRHH %s con tipo desconocido.", entrante.id)
                continue
            mensaje = MensajeRRHH(
                entrante.id, entrante.telefono, entrante.legajo, entrante.nombre, entrante.empresa, tipo,
                entrante.texto[:1000], entrante.recibido_en, entrante.archivo,
                entrante.archivo_tipo if entrante.archivo is not None else "", entrante.archivo_nombre or "",
            )
            if tipo is TipoMensaje.CERTIFICADO and mensaje.archivo is not None:
                mensaje = replace(self._leer_mensaje(mensaje), aviso_pendiente=True)
            self.repo.guardar(mensaje)
            nuevos += 1
        if recibidos:
            self.puerta.confirmar_mensajes([m.id for m in recibidos])
        return nuevos

    def _leer_mensaje(self, mensaje: MensajeRRHH) -> MensajeRRHH:
        """Corre el lector de certificados. Si falla, el mensaje queda igual con los campos vacíos."""
        assert mensaje.archivo is not None
        nombre = f"certificado-{mensaje.id}{EXTENSIONES[mensaje.archivo_tipo]}"
        try:
            lectura = limpiar_lectura(self._leer(nombre, mensaje.archivo, mensaje.legajo) or {})
        except Exception as exc:  # noqa: BLE001 - un lector caído no frena la bandeja
            _registro.warning("No se pudo leer el certificado %s: %s", mensaje.id, exc.__class__.__name__)
            return replace(mensaje, lectura={}, lectura_error="No se pudo leer el certificado.")
        return replace(mensaje, lectura=lectura)

    def _avisar_pendientes(self) -> None:
        """Le manda al empleado lo que se leyó (o que RRHH lo revisa). Si la base no responde, se
        vuelve a intentar en la próxima sincronización; la base no lo manda dos veces."""
        for mensaje in self.repo.listar():
            if not mensaje.aviso_pendiente:
                continue
            texto, pide = texto_confirmacion(mensaje.lectura)
            try:
                self.puerta.avisar_lectura(mensaje.id, texto, pide)
            except Exception:  # noqa: BLE001
                _registro.warning("No se pudo avisar al empleado del certificado %s.", mensaje.id, exc_info=True)
                continue
            self.repo.guardar(replace(mensaje, aviso_pendiente=False,
                                      confirmacion="esperando" if pide else "sin_pedir"))

    def _recibir_cvs(self) -> None:
        recibidos = self.puerta.tomar_cvs()
        guardados = []
        for cv in recibidos:
            try:
                self._incorporar_cv(cv)
            except Exception:  # noqa: BLE001 - queda en la DMZ y se vuelve a intentar
                _registro.warning("No se pudo incorporar el CV %s de WhatsApp.", cv.id, exc_info=True)
                continue
            guardados.append(cv.id)
        if guardados:
            self.puerta.confirmar_cvs(guardados)

    def _actualizar_confirmaciones(self) -> None:
        esperando = {m.id: m for m in self.repo.listar()
                     if m.tipo is TipoMensaje.CERTIFICADO and m.confirmacion in {"esperando", "corrigiendo"}}
        if not esperando:
            return
        for mensaje_id, respuesta in self.puerta.confirmaciones(list(esperando)).items():
            mensaje = esperando.get(mensaje_id)
            if mensaje is None:
                continue
            nuevo = replace(mensaje, confirmacion=respuesta.confirmacion, confirmacion_vence=respuesta.vence,
                            correccion=respuesta.correccion or "", respondido_en=respuesta.respondido_en)
            if nuevo != mensaje:
                self.repo.guardar(nuevo)

    # --- Consultas -----------------------------------------------------------
    def obtener(self, mensaje_id: str) -> MensajeRRHH:
        mensaje = self.repo.obtener(mensaje_id)
        if mensaje is None:
            raise LookupError("No existe ese mensaje.")
        return mensaje

    def estado_confirmacion(self, m: MensajeRRHH) -> str:
        """Lo que se muestra: sin pedir, esperando, corrigiendo, confirmado, no coincide o sin confirmar."""
        if m.confirmacion in {"esperando", "corrigiendo"} and m.confirmacion_vence and m.confirmacion_vence <= self._reloj():
            return "sin_confirmar" if m.confirmacion == "esperando" else "no_coincide"
        return m.confirmacion

    def vista(self, m: MensajeRRHH) -> dict[str, Any]:
        return {
            "id": m.id, "legajo": m.legajo, "nombre": m.nombre, "empresa": m.empresa, "tipo": m.tipo.value,
            "texto": m.texto, "recibido_en": m.recibido_en, "con_archivo": m.archivo is not None,
            "archivo_tipo": m.archivo_tipo, "archivo_nombre": m.archivo_nombre,
            "lectura": m.lectura or {}, "lectura_error": m.lectura_error,
            "confirmacion": self.estado_confirmacion(m), "correccion": m.correccion,
            "respondido_en": m.respondido_en, "estado": m.estado.value, "resuelto_por": m.resuelto_por,
            "resuelto_en": m.resuelto_en, "nota": m.nota, "adjunto_id": m.adjunto_id,
            "datos_confirmados": m.datos_confirmados,
        }

    def listar(self, estado: str | None = None) -> list[dict[str, Any]]:
        filas = [self.vista(m) for m in self.repo.listar()]
        if estado:
            filas = [f for f in filas if f["estado"] == estado]
        return sorted(filas, key=lambda f: (f["estado"] != EstadoMensaje.PENDIENTE.value, -f["recibido_en"].timestamp()))

    # --- Acciones de RRHH ----------------------------------------------------
    def _pendiente(self, mensaje_id: str) -> MensajeRRHH:
        mensaje = self.obtener(mensaje_id)
        if mensaje.estado is not EstadoMensaje.PENDIENTE:
            raise ValueError("Ese mensaje ya se resolvió.")
        return mensaje

    def pasar_al_legajo(self, mensaje_id: str, datos: dict[str, Any], actor: str) -> MensajeRRHH:
        """El certificado se guarda como adjunto del legajo del empleado, con los datos que RRHH confirmó."""
        with self._bloqueo:
            mensaje = self._pendiente(mensaje_id)
            if mensaje.tipo is not TipoMensaje.CERTIFICADO or mensaje.archivo is None:
                raise ValueError("Sólo un certificado con su archivo pasa al legajo.")
            desde, hasta, dias = _fecha(datos.get("desde")), _fecha(datos.get("hasta")), datos.get("dias")
            if desde and hasta and hasta < desde:
                raise ValueError("La fecha hasta no puede ser anterior a la fecha desde.")
            if dias is not None and _dias(dias) is None:
                raise ValueError("Los días tienen que ser entre 1 y 365.")
            if desde and hasta and dias is not None and int(dias) != (hasta - desde).days + 1:
                raise ValueError(f"Los días deben coincidir con las fechas: {(hasta - desde).days + 1}.")
            nombre = (str(datos.get("nombre") or "").strip()
                      or f"Certificado médico {mensaje.recibido_en:%Y-%m-%d}")[:120]
            if not nombre.lower().endswith(EXTENSIONES[mensaje.archivo_tipo]):
                nombre += EXTENSIONES[mensaje.archivo_tipo]
            adjunto_id = self._adjuntar(mensaje.legajo, nombre, mensaje.archivo, actor)
            confirmados = {
                "dias": _dias(dias) if dias is not None else None,
                "desde": desde.isoformat() if desde else None, "hasta": hasta.isoformat() if hasta else None,
                "profesional": str(datos.get("profesional") or "").strip()[:120],
                "resumen": str(datos.get("resumen") or "").strip()[:500],
                "nombre_adjunto": nombre,
            }
            resuelto = replace(mensaje, estado=EstadoMensaje.EN_LEGAJO, resuelto_por=actor, resuelto_en=self._reloj(),
                               adjunto_id=adjunto_id, datos_confirmados=confirmados,
                               nota=str(datos.get("nota") or "").strip()[:300])
            self.repo.guardar(resuelto)
            return resuelto

    def atender(self, mensaje_id: str, nota: str, actor: str) -> MensajeRRHH:
        """Pedido de EPP resuelto (no hay en EPP un pedido de entrega al que enlazarlo: queda la nota)."""
        with self._bloqueo:
            mensaje = self._pendiente(mensaje_id)
            if mensaje.tipo is not TipoMensaje.EPP:
                raise ValueError("Sólo un pedido de EPP se marca como atendido.")
            resuelto = replace(mensaje, estado=EstadoMensaje.ATENDIDO, resuelto_por=actor, resuelto_en=self._reloj(),
                               nota=nota.strip()[:300])
            self.repo.guardar(resuelto)
            return resuelto

    def descartar(self, mensaje_id: str, motivo: str, actor: str) -> MensajeRRHH:
        if not motivo.strip():
            raise ValueError("Indicá por qué se descarta.")
        with self._bloqueo:
            mensaje = self._pendiente(mensaje_id)
            resuelto = replace(mensaje, estado=EstadoMensaje.DESCARTADO, resuelto_por=actor,
                               resuelto_en=self._reloj(), nota=motivo.strip()[:300])
            self.repo.guardar(resuelto)
            return resuelto

    # --- Recorridos del micro --------------------------------------------------
    def recorridos(self) -> list[dict[str, Any]]:
        return [{**r, "sede_nombre": self.sedes.get(r["sede"], r["sede"])} for r in self.puerta.recorridos()]

    def guardar_recorrido(self, recorrido_id: int | None, sede: str, nombre: str, activo: bool,
                          actor: str) -> dict[str, Any]:
        if sede not in self.sedes:
            raise ValueError("Elegí la bodega del recorrido.")
        nombre = " ".join(nombre.split())
        if not 2 <= len(nombre) <= 80:
            raise ValueError("El nombre del recorrido tiene que tener entre 2 y 80 letras.")
        return self.puerta.guardar_recorrido(recorrido_id, sede, nombre, activo, actor)
