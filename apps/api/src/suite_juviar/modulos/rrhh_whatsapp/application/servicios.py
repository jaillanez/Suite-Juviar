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
    EstadoSalud,
    MensajeRRHH,
    TipoMensaje,
)
from ..domain.puertos import DestinoSalud, PuertaDMZ, RepositorioBandeja

_registro = logging.getLogger(__name__)

# Lo que se le muestra a RRHH de la lectura del certificado. El resumen y el texto leído pueden
# traer el diagnóstico: quedan sólo en Salud, con su propio permiso.
CAMPOS_LECTURA = ("dias_detectados", "fecha_desde", "fecha_hasta", "fecha_reintegro", "profesional",
                  "tipo_accidente", "paciente_nombre", "paciente_dni", "motor", "mensaje")
# Lo que se guarda aparte, sólo para Salud (perfil médico).
CAMPOS_SALUD = ("diagnostico_codigo", "diagnostico_texto", "resumen")
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


def lectura_para_salud(lectura: dict[str, Any]) -> dict[str, str]:
    datos = {clave: str(lectura.get(clave) or "").strip()[:500] for clave in CAMPOS_SALUD}
    datos["diagnostico_codigo"] = datos["diagnostico_codigo"].upper()[:50]
    return {clave: valor for clave, valor in datos.items() if valor}


def _datos_certificado(datos: dict[str, Any]) -> tuple[date | None, date | None, int | None]:
    """Fechas y días de un certificado, validados entre sí. Sin días, salen de las fechas."""
    desde, hasta, dias = _fecha(datos.get("desde")), _fecha(datos.get("hasta")), datos.get("dias")
    if desde and hasta and hasta < desde:
        raise ValueError("La fecha hasta no puede ser anterior a la fecha desde.")
    if dias is not None and _dias(dias) is None:
        raise ValueError("Los días tienen que ser entre 1 y 365.")
    if desde and hasta and dias is not None and int(dias) != (hasta - desde).days + 1:
        raise ValueError(f"Los días deben coincidir con las fechas: {(hasta - desde).days + 1}.")
    if dias is None and desde and hasta:
        dias = (hasta - desde).days + 1
    return desde, hasta, _dias(dias) if dias is not None else None


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
        salud: DestinoSalud | None = None,
    ) -> None:
        self.repo = repo
        self.puerta = puerta
        self._leer = leer_certificado  # (nombre con extensión, contenido, legajo)
        self._adjuntar = adjuntar_legajo  # (legajo, nombre, contenido, actor) -> id del adjunto
        self._incorporar_cv = incorporar_cv
        self.sedes = sedes
        self._reloj = reloj
        self._salud = salud
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
            cruda = self._leer(nombre, mensaje.archivo, mensaje.legajo) or {}
        except Exception as exc:  # noqa: BLE001 - un lector caído no frena la bandeja
            _registro.warning("No se pudo leer el certificado %s: %s", mensaje.id, exc.__class__.__name__)
            return replace(mensaje, lectura={}, lectura_error="No se pudo leer el certificado.")
        return replace(mensaje, lectura=limpiar_lectura(cruda), lectura_salud=lectura_para_salud(cruda))

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
            # De Salud, RRHH sólo ve si quedó cargado o pendiente; nunca el diagnóstico ni el motivo.
            "salud": m.salud.value,
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
            desde, hasta, dias = _datos_certificado(datos)
            nombre = (str(datos.get("nombre") or "").strip()
                      or f"Certificado médico {mensaje.recibido_en:%Y-%m-%d}")[:120]
            if not nombre.lower().endswith(EXTENSIONES[mensaje.archivo_tipo]):
                nombre += EXTENSIONES[mensaje.archivo_tipo]
            adjunto_id = self._adjuntar(mensaje.legajo, nombre, mensaje.archivo, actor)
            confirmados = {
                "dias": dias,
                "desde": desde.isoformat() if desde else None, "hasta": hasta.isoformat() if hasta else None,
                "profesional": str(datos.get("profesional") or "").strip()[:120],
                "nombre_adjunto": nombre,
            }
            resuelto = replace(mensaje, estado=EstadoMensaje.EN_LEGAJO, resuelto_por=actor, resuelto_en=self._reloj(),
                               adjunto_id=adjunto_id, datos_confirmados=confirmados,
                               nota=str(datos.get("nota") or "").strip()[:300])
            self.repo.guardar(resuelto)
            # El legajo ya tiene el archivo; ahora Salud. Si no se puede solo, lo completa el médico.
            resuelto = self._cargar_en_salud(resuelto, resuelto.lectura_salud.get("diagnostico_codigo", ""),
                                             confirmados, actor, automatico=True)
            self.repo.guardar(resuelto)
            return resuelto

    def _cargar_en_salud(self, mensaje: MensajeRRHH, diagnostico: str, datos: dict[str, Any], actor: str,
                         automatico: bool) -> MensajeRRHH:
        """Carga el certificado en Salud. Automático (lo dispara RRHH): si falta algo o Salud lo
        rechaza, queda pendiente para el perfil médico. A mano (el médico): el error se informa."""
        assert mensaje.archivo is not None
        desde, hasta, dias = _fecha(datos.get("desde")), _fecha(datos.get("hasta")), _dias(datos.get("dias"))
        profesional = str(datos.get("profesional") or "").strip()
        faltan = [nombre for nombre, valor in (("diagnóstico", diagnostico.strip()), ("fecha desde", desde),
                                               ("fecha hasta", hasta), ("días", dias),
                                               ("profesional", profesional)) if not valor]
        pendiente = replace(mensaje, salud=EstadoSalud.PENDIENTE)
        if self._salud is None:
            if not automatico:
                raise RuntimeError("Salud no está conectada.")
            return replace(pendiente, salud_motivo="Salud no está conectada.")
        if faltan:
            if not automatico:
                raise ValueError(f"Falta: {', '.join(faltan)}.")
            return replace(pendiente, salud_motivo=f"Falta: {', '.join(faltan)}.")
        assert desde and hasta and dias
        resumen = str(datos.get("resumen") or mensaje.lectura_salud.get("resumen") or "")[:500]
        tipo_accidente = str(datos.get("tipo_accidente") or (mensaje.lectura or {}).get("tipo_accidente")
                             or "NO_INFORMADO")
        try:
            certificado_id = self._salud.cargar(
                mensaje.legajo, diagnostico.strip().upper(), desde, hasta, dias, profesional,
                str(mensaje.datos_confirmados.get("nombre_adjunto") or f"certificado-{mensaje.id}"),
                mensaje.archivo, resumen, tipo_accidente)
        except ValueError as exc:
            if not automatico:
                raise
            return replace(pendiente, salud_motivo=str(exc)[:300])
        except Exception:  # el legajo ya quedó; Salud se completa a mano
            if not automatico:
                raise
            _registro.warning("No se pudo cargar en Salud el certificado %s.", mensaje.id, exc_info=True)
            return replace(pendiente, salud_motivo="Salud no respondió.")
        self._salud.auditar(actor, mensaje.legajo, "CARGA_CERTIFICADO_WHATSAPP_AUTOMATICA" if automatico
                            else "CARGA_CERTIFICADO_WHATSAPP")
        return replace(mensaje, salud=EstadoSalud.CARGADO, salud_motivo="", salud_certificado_id=certificado_id,
                       salud_por=actor, salud_en=self._reloj())

    # --- Salud (perfil médico) -------------------------------------------------
    def _pendiente_salud(self, mensaje_id: str) -> MensajeRRHH:
        mensaje = self.obtener(mensaje_id)
        if mensaje.salud is not EstadoSalud.PENDIENTE or mensaje.archivo is None:
            raise LookupError("Ese certificado no está pendiente de Salud.")
        return mensaje

    def vista_salud(self, m: MensajeRRHH) -> dict[str, Any]:
        """Lo que ve el servicio médico: lo que confirmó RRHH y el diagnóstico leído, si hubo."""
        return {
            "id": m.id, "legajo": m.legajo, "nombre": m.nombre, "empresa": m.empresa,
            "recibido_en": m.recibido_en, "archivo_tipo": m.archivo_tipo,
            "datos_confirmados": m.datos_confirmados,
            "tipo_accidente": (m.lectura or {}).get("tipo_accidente", "NO_INFORMADO"),
            "diagnostico_codigo": m.lectura_salud.get("diagnostico_codigo", ""),
            "diagnostico_texto": m.lectura_salud.get("diagnostico_texto", ""),
            "resumen": m.lectura_salud.get("resumen", ""), "motivo": m.salud_motivo,
            "pasado_por": m.resuelto_por, "pasado_en": m.resuelto_en, "salud": m.salud.value,
            "salud_por": m.salud_por, "salud_en": m.salud_en,
        }

    def pendientes_salud(self, actor: str) -> list[dict[str, Any]]:
        filas = [m for m in self.repo.listar() if m.salud is EstadoSalud.PENDIENTE]
        if self._salud is not None:
            self._salud.auditar(actor, None, "CONSULTA_PENDIENTES_WHATSAPP")
        return [self.vista_salud(m) for m in sorted(filas, key=lambda m: m.recibido_en)]

    def archivo_salud(self, mensaje_id: str, actor: str) -> MensajeRRHH:
        mensaje = self._pendiente_salud(mensaje_id)
        if self._salud is not None:
            self._salud.auditar(actor, mensaje.legajo, "CONSULTA_ADJUNTO_WHATSAPP")
        return mensaje

    def completar_salud(self, mensaje_id: str, datos: dict[str, Any], actor: str) -> MensajeRRHH:
        """El médico elige el diagnóstico del catálogo (y corrige fechas o profesional si hace falta)."""
        with self._bloqueo:
            mensaje = self._pendiente_salud(mensaje_id)
            confirmados = mensaje.datos_confirmados
            elegidos = {clave: datos.get(clave) if datos.get(clave) not in (None, "") else confirmados.get(clave)
                        for clave in ("desde", "hasta", "dias", "profesional")}
            if datos.get("desde") or datos.get("hasta"):
                # Si el médico corrige las fechas, los días salen de las fechas nuevas.
                elegidos["dias"] = datos.get("dias")
            desde, hasta, dias = _datos_certificado(elegidos)
            elegidos.update(desde=desde, hasta=hasta, dias=dias, resumen=datos.get("resumen"),
                            tipo_accidente=datos.get("tipo_accidente"))
            cargado = self._cargar_en_salud(mensaje, str(datos.get("diagnostico_codigo") or ""), elegidos, actor,
                                            automatico=False)
            self.repo.guardar(cargado)
            return cargado

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

    def personal(self) -> list[dict[str, Any]]:
        return [{**p, "recorrido_sede_nombre": self.sedes.get(p.get("recorrido_sede") or "",
                                                              p.get("recorrido_sede") or "")}
                for p in self.puerta.personal()]

    def asignar_recorrido(self, telefono: str, recorrido_id: int | None, actor: str) -> dict[str, Any]:
        """RRHH sólo cambia el recorrido; el alta, la baja y los datos siguen en «Personal en el bot»."""
        return self.puerta.asignar_recorrido(telefono, recorrido_id, actor)
