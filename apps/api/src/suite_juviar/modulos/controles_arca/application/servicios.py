"""Facturas de proveedores, sus cinco controles de ARCA, los listados y el certificado."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from threading import RLock
from typing import Any
from uuid import uuid4

from ..domain.modelos import (
    AMBIENTES,
    AUTORIZACIONES,
    DESCRIPCION_CONTROL,
    EMPRESAS,
    HORA_ARGENTINA,
    NOMBRES_CONTROL,
    NOMBRES_ESTADO,
    TIPOS_COMPROBANTE,
    AccesoARCA,
    Control,
    Credencial,
    ErrorARCA,
    Estado,
    Factura,
    Padron,
    Parametros,
    Resultado,
    evaluar_apocrifa,
    evaluar_constancia,
    evaluar_constatacion,
    evaluar_rg18,
    nombre_pdf,
    validar_cuit,
)
from ..domain.puertos import (
    Certificados,
    Cifrador,
    ConectorARCA,
    DescargaPadrones,
    GeneradorPDF,
    RepositorioControles,
)

_registro = logging.getLogger(__name__)
PARAMETROS = "controles-arca"
PADRONES = {"apocrifas": "Facturas apócrifas", "rg18": "Agentes de retención (RG 18)"}
MAXIMO_PDF = 10 * 1024 * 1024
# Estados en los que se puede subir a mano la constancia (además del control impositivo).
_SUBIBLES = {Estado.PENDIENTE, Estado.ERROR, Estado.SIN_CONFIGURAR}
_FALLA_ARCA = "No se pudo consultar ARCA. Probá de nuevo más tarde."


class FaltaClaveServidor(RuntimeError):
    """El servidor no tiene la clave para cifrar el certificado (SJ_CLAVE_PARAMETROS)."""


def _ahora() -> datetime:
    return datetime.now(UTC)


def _dia(momento: datetime) -> date:
    return momento.astimezone(HORA_ARGENTINA).date()


def _hora(momento: datetime) -> str:
    return momento.astimezone(HORA_ARGENTINA).strftime("%d/%m/%Y %H:%M")


def _pesos(valor: float) -> str:
    return "$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class GestionarControles:
    def __init__(self, repo: RepositorioControles, pdf: GeneradorPDF, descargas: DescargaPadrones,
                 conector: ConectorARCA | None = None, certificados: Certificados | None = None,
                 cifrador: Cifrador | None = None, reloj=_ahora) -> None:
        self.repo = repo
        self.pdf = pdf
        self.descargas = descargas
        self.conector = conector
        self.certificados = certificados
        self.cifrador = cifrador
        self._reloj = reloj
        self._bloqueo = RLock()
        self._padrones: dict[str, Padron] = {}

    # --- Parámetros ------------------------------------------------------
    def parametros(self) -> Parametros:
        return self.repo.parametros.get(PARAMETROS) or Parametros()

    def guardar_parametros(self, datos: dict[str, Any], actor: str) -> Parametros:
        nuevos = Parametros(
            controles_activos=frozenset(int(c) for c in datos["controles_activos"]),
            excluir_controlador_fiscal=bool(datos["excluir_controlador_fiscal"]),
            ambiente=datos["ambiente"],
            cuit_representante=validar_cuit(datos["cuit_representante"], "El CUIT del representante"),
            cuit_empresas={e: validar_cuit(c, f"El CUIT de {e}") if (c := (datos["cuit_empresas"].get(e) or "").strip())
                           else "" for e in EMPRESAS},
            url_apocrifas=datos["url_apocrifas"], url_rg18=datos["url_rg18"],
            enlaces_impositivo=tuple(e.strip() for e in datos["enlaces_impositivo"] if e.strip()),
            actualizado_por=actor, actualizado_en=self._reloj(),
        )
        self.repo.parametros[PARAMETROS] = nuevos
        return nuevos

    def vista_parametros(self) -> dict[str, Any]:
        p = self.parametros()
        return {
            "controles_activos": sorted(p.controles_activos), "excluir_controlador_fiscal": p.excluir_controlador_fiscal,
            "ambiente": p.ambiente, "cuit_representante": p.cuit_representante, "cuit_empresas": dict(p.cuit_empresas),
            "url_apocrifas": p.url_apocrifas, "url_rg18": p.url_rg18, "enlaces_impositivo": list(p.enlaces_impositivo),
            "actualizado_por": p.actualizado_por, "actualizado_en": p.actualizado_en,
        }

    def catalogo(self) -> dict[str, Any]:
        p = self.parametros()
        acceso, motivo = self._acceso(p, descifrar=False)
        return {
            "empresas": list(EMPRESAS), "tipos_comprobante": {str(k): v for k, v in TIPOS_COMPROBANTE.items()},
            "autorizaciones": AUTORIZACIONES, "estados": {e.value: n for e, n in NOMBRES_ESTADO.items()},
            "controles": [{"numero": int(c), "nombre": NOMBRES_CONTROL[c], "descripcion": DESCRIPCION_CONTROL[c],
                           "activo": int(c) in p.controles_activos} for c in Control],
            "enlaces_impositivo": list(p.enlaces_impositivo), "ambiente": p.ambiente,
            "ambiente_nombre": AMBIENTES[p.ambiente],
            "faltantes": [m for m in (
                motivo if acceso is None else "",
                *(f"Falta cargar en Parámetros el CUIT de {e}." for e in EMPRESAS if not p.cuit_empresas.get(e)),
            ) if m],
            "padrones": self.padrones_info(),
        }

    # --- Facturas --------------------------------------------------------
    def obtener(self, factura_id: str) -> Factura:
        factura = self.repo.facturas.get(factura_id)
        if factura is None:
            raise LookupError("No existe esa factura.")
        return factura

    def crear_factura(self, datos: dict[str, Any], actor: str) -> Factura:
        fecha = datos["fecha"]
        if fecha > _dia(self._reloj()):
            raise ValueError("La fecha de la factura no puede ser posterior a hoy.")
        autorizacion = datos["autorizacion"]
        factura = Factura(
            uuid4().hex, datos["empresa"], "".join(str(datos["cuit_emisor"]).split()).replace("-", ""),
            (datos.get("razon_social") or "").strip(), int(datos["tipo_comprobante"]), int(datos["punto_venta"]),
            int(datos["numero"]), fecha, float(datos["importe_total"]), autorizacion,
            "".join((datos.get("codigo_autorizacion") or "").split()), actor, self._reloj(),
        )
        with self._bloqueo:
            if any((f.empresa, f.cuit_emisor, f.tipo_comprobante, f.punto_venta, f.numero)
                   == (factura.empresa, factura.cuit_emisor, factura.tipo_comprobante, factura.punto_venta,
                       factura.numero) for f in self.repo.facturas.values()):
                raise ValueError("Esa factura ya está cargada para esa empresa.")
            self.repo.facturas[factura.id] = factura
        return factura

    def listar(self, solo_alertas: bool = False) -> list[dict[str, Any]]:
        facturas = sorted(self.repo.facturas.values(), key=lambda f: f.cargada_en, reverse=True)
        return [self.vista(f) for f in facturas if not solo_alertas or f.alerta]

    def vista(self, factura: Factura) -> dict[str, Any]:
        controles = []
        for control in Control:
            r = factura.resultado(control)
            controles.append({
                "numero": int(control), "nombre": NOMBRES_CONTROL[control],
                "estado": r.estado.value if r else "sin_correr",
                "estado_nombre": NOMBRES_ESTADO[r.estado] if r else "Sin controlar",
                "detalle": r.detalle if r else "", "fuente": r.fuente if r else "",
                "fecha": r.fecha if r else None, "actor": r.actor if r else "", "nota": r.nota if r else "",
                "archivo": f"{r.archivo}.pdf" if r and r.archivo else "",
                "puede_subir": r is not None and (control is Control.IMPOSITIVO or r.estado in _SUBIBLES),
            })
        return {
            "id": factura.id, "empresa": factura.empresa, "cuit_emisor": factura.cuit_emisor,
            "razon_social": factura.razon_social, "tipo_comprobante": factura.tipo_comprobante,
            "tipo_nombre": TIPOS_COMPROBANTE[factura.tipo_comprobante], "punto_venta": factura.punto_venta,
            "numero": factura.numero, "comprobante": factura.comprobante, "fecha": factura.fecha,
            "importe_total": factura.importe_total, "autorizacion": factura.autorizacion,
            "autorizacion_nombre": AUTORIZACIONES[factura.autorizacion],
            "codigo_autorizacion": factura.codigo_autorizacion, "cargada_por": factura.cargada_por,
            "cargada_en": factura.cargada_en, "alerta": factura.alerta, "controles": controles,
            "controlada": bool(factura.resultados),
        }

    # --- Controles -------------------------------------------------------
    def correr(self, factura_id: str, actor: str) -> Factura:
        factura = self.obtener(factura_id)
        p = self.parametros()
        acceso, motivo = self._acceso(p)
        resultados = tuple(self._correr_uno(c, factura, p, acceso, motivo, actor) for c in Control)
        with self._bloqueo:
            actual = replace(self.obtener(factura_id), resultados=resultados)
            self.repo.facturas[actual.id] = actual
        return actual

    def _resultado(self, control: Control, estado: Estado, detalle: str, actor: str, fuente: str = "") -> Resultado:
        return Resultado(control, estado, detalle, fuente, self._reloj(), actor)

    def _correr_uno(self, control: Control, factura: Factura, p: Parametros, acceso: AccesoARCA | None,
                    motivo: str, actor: str) -> Resultado:
        previo = factura.resultado(control)
        if int(control) not in p.controles_activos:
            return self._resultado(control, Estado.NO_APLICA, "Este control está apagado en Parámetros.", actor)
        if control is Control.IMPOSITIVO:
            return self._manual(factura, previo, actor)
        if control is Control.COMPROBANTE and factura.autorizacion == "CF":
            if p.excluir_controlador_fiscal:
                return self._resultado(control, Estado.NO_APLICA,
                                       "Factura de controlador fiscal: según Parámetros no se controla.", actor)
            if previo is not None and previo.archivo and previo.estado in {Estado.OK, Estado.ALERTA}:
                return previo
            return self._resultado(control, Estado.PENDIENTE,
                                   "ARCA no constata por servicio web las facturas de controlador fiscal: "
                                   "controlala a mano y subí el PDF.", actor)
        try:
            if control in {Control.INSCRIPCION, Control.COMPROBANTE}:
                cuit_empresa = p.cuit_empresas.get(factura.empresa, "")
                if acceso is None or self.conector is None:
                    return self._resultado(control, Estado.SIN_CONFIGURAR, motivo, actor)
                if not cuit_empresa:
                    return self._resultado(control, Estado.SIN_CONFIGURAR,
                                           f"Falta cargar en Parámetros el CUIT de {factura.empresa}.", actor)
                ambiente = AMBIENTES[p.ambiente]
                # Se consulta con el CUIT dueño del certificado: ARCA no deja delegar estos servicios
                # web a una persona, y ninguno de los dos exige ser la empresa. La empresa va como
                # receptora de la factura en la constatación.
                if control is Control.INSCRIPCION:
                    estado, detalle = evaluar_constancia(
                        self.conector.constancia(acceso, p.cuit_representante, factura.cuit_emisor))
                    fuente = f"ARCA, constancia de inscripción (padrón A5), {ambiente}"
                else:
                    estado, detalle = evaluar_constatacion(
                        self.conector.constatar(acceso, p.cuit_representante, factura, cuit_empresa),
                        factura.autorizacion)
                    fuente = f"ARCA, constatación de comprobantes (WSCDC), {ambiente}"
            else:
                padron = self._padron("apocrifas" if control is Control.APOCRIFAS else "rg18")
                if control is Control.APOCRIFAS:
                    estado, detalle = evaluar_apocrifa(padron, factura.cuit_emisor)
                else:
                    estado, detalle = evaluar_rg18(padron, factura.cuit_emisor, factura.fecha)
                fuente = (f"ARCA, listado completo de {PADRONES[padron.nombre].lower()} "
                          f"bajado el {_hora(padron.descargado_en)} de {padron.url}")
        except ErrorARCA as exc:
            _registro.warning("Control %s de la factura %s: %s", int(control), factura.id, exc)
            return self._resultado(control, Estado.ERROR, str(exc)[:300] or _FALLA_ARCA, actor)
        except Exception:  # noqa: BLE001 - una consulta caída no frena los demás controles
            _registro.exception("Control %s de la factura %s falló.", int(control), factura.id)
            return self._resultado(control, Estado.ERROR, _FALLA_ARCA, actor)
        resultado = self._resultado(control, estado, detalle, actor, fuente)
        return self._guardar_pdf(factura, resultado, p)

    def _manual(self, factura: Factura, previo: Resultado | None, actor: str) -> Resultado:
        control = Control.IMPOSITIVO
        if previo is not None and previo.archivo and previo.estado in {Estado.OK, Estado.ALERTA}:
            return previo
        # Si ese día ya se subió la constancia del mismo proveedor con otra factura, se reusa.
        hoy = _dia(self._reloj())
        for otra in self.repo.facturas.values():
            r = otra.resultado(control)
            if (otra.id != factura.id and otra.cuit_emisor == factura.cuit_emisor and r is not None and r.archivo
                    and r.estado in {Estado.OK, Estado.ALERTA} and _dia(r.fecha) == hoy
                    and (contenido := self.repo.archivos.get(f"{otra.id}:{int(control)}"))):
                self.repo.archivos[f"{factura.id}:{int(control)}"] = contenido
                return replace(r, detalle=f"{r.detalle} Constancia del día, subida con {otra.comprobante}.")
        return self._resultado(control, Estado.PENDIENTE,
                               "Falta subir el PDF de ARCA (Reproweb, agente de retención y consulta puntual).",
                               actor)

    def _guardar_pdf(self, factura: Factura, r: Resultado, p: Parametros) -> Resultado:
        nombre = nombre_pdf(factura.cuit_emisor, r.control, _dia(r.fecha), factura.numero)
        filas = [
            ("Resultado", NOMBRES_ESTADO[r.estado]),
            ("Detalle", r.detalle),
            ("Empresa que recibió la factura", f"{factura.empresa} (CUIT {p.cuit_empresas.get(factura.empresa) or 'sin cargar'})"),
            ("Proveedor", f"{factura.razon_social or 'Sin razón social cargada'} (CUIT {factura.cuit_emisor})"),
            ("Comprobante", factura.comprobante),
            ("Fecha de la factura", factura.fecha.strftime("%d/%m/%Y")),
            ("Importe total", _pesos(factura.importe_total)),
            ("Autorización", f"{AUTORIZACIONES[factura.autorizacion]} {factura.codigo_autorizacion}".strip()),
            ("Fuente consultada", r.fuente),
            ("Fecha y hora de la consulta", _hora(r.fecha)),
            ("Consultó", r.actor),
        ]
        titulo = f"Control {int(r.control)}: {NOMBRES_CONTROL[r.control]}"
        self.repo.archivos[f"{factura.id}:{int(r.control)}"] = self.pdf.constancia(titulo, filas, r.estado is Estado.ALERTA)
        return replace(r, archivo=nombre)

    def subir_constancia(self, factura_id: str, numero: int, contenido: bytes, resultado: str, nota: str,
                         actor: str) -> Factura:
        control = Control(numero)
        if not contenido.startswith(b"%PDF-"):
            raise ValueError("El archivo tiene que ser un PDF.")
        if len(contenido) > MAXIMO_PDF:
            raise ValueError("El PDF es muy grande: el máximo es 10 MB.")
        if resultado not in {"ok", "alerta"}:
            raise ValueError("Elegí si el control dio bien o con alerta.")
        nota = (nota or "").strip()[:300]
        if resultado == "alerta" and not nota:
            raise ValueError("Escribí qué encontraste en ARCA.")
        with self._bloqueo:
            factura = self.obtener(factura_id)
            previo = factura.resultado(control)
            if previo is None:
                raise ValueError("Primero corré los controles de la factura.")
            if control is not Control.IMPOSITIVO and previo.estado not in _SUBIBLES:
                raise ValueError("Este control ya tiene resultado de ARCA: no se reemplaza a mano.")
            ahora = self._reloj()
            nuevo = Resultado(control, Estado(resultado),
                              "Controlado a mano en ARCA con clave fiscal." + (f" {nota}" if nota else ""),
                              "ARCA con clave fiscal: PDF subido por quien hizo el control", ahora, actor,
                              nombre_pdf(factura.cuit_emisor, control, _dia(ahora), factura.numero), nota)
            self.repo.archivos[f"{factura.id}:{int(control)}"] = contenido
            actual = replace(factura, resultados=tuple(nuevo if r.control == control else r
                                                       for r in factura.resultados))
            self.repo.facturas[actual.id] = actual
        return actual

    def archivo(self, factura_id: str, numero: int) -> tuple[str, bytes]:
        factura = self.obtener(factura_id)
        r = factura.resultado(Control(numero))
        contenido = self.repo.archivos.get(f"{factura.id}:{int(numero)}") if r and r.archivo else None
        if r is None or contenido is None:
            raise LookupError("Ese control no tiene PDF guardado.")
        return f"{r.archivo}.pdf", contenido

    # --- Listados completos de ARCA -------------------------------------
    def _padron(self, nombre: str) -> Padron:
        padron = self._padrones.get(nombre) or self.repo.padrones.get(nombre)
        if padron is None:
            padron = self.actualizar_padron(nombre)
        self._padrones[nombre] = padron
        return padron

    def actualizar_padron(self, nombre: str) -> Padron:
        if nombre not in PADRONES:
            raise LookupError("No existe ese listado.")
        p = self.parametros()
        url = p.url_apocrifas if nombre == "apocrifas" else p.url_rg18
        try:
            generado, registros = self.descargas.descargar(nombre, url)
        except (ErrorARCA, ValueError):
            raise
        except Exception as exc:
            _registro.warning("No se pudo bajar el listado %s de %s: %s", nombre, url, exc)
            raise ErrorARCA(f"No se pudo bajar de ARCA el listado de {PADRONES[nombre].lower()}.") from exc
        if not registros:
            raise ErrorARCA(f"El listado de {PADRONES[nombre].lower()} vino vacío: se mantiene el anterior.")
        padron = Padron(nombre, url, self._reloj(), generado, registros)
        self.repo.padrones[nombre] = padron
        self._padrones[nombre] = padron
        return padron

    def actualizar_vencidos(self, horas: float = 24) -> list[str]:
        """Baja los listados que no se actualizaron en las últimas ``horas``; devuelve los bajados."""
        bajados = []
        for nombre in PADRONES:
            padron = self.repo.padrones.get(nombre)
            if padron is not None and self._reloj() - padron.descargado_en < timedelta(hours=horas):
                continue
            try:
                self.actualizar_padron(nombre)
                bajados.append(nombre)
            except Exception:  # noqa: BLE001 - si uno falla se intenta el otro
                _registro.exception("No se pudo actualizar el listado %s.", nombre)
        return bajados

    def padrones_info(self) -> list[dict[str, Any]]:
        info = []
        for nombre, titulo in PADRONES.items():
            padron = self._padrones.get(nombre) or self.repo.padrones.get(nombre)
            if padron is not None:
                self._padrones[nombre] = padron
            info.append({"nombre": nombre, "titulo": titulo,
                         "descargado_en": padron.descargado_en if padron else None,
                         "generado": padron.generado if padron else "",
                         "cuits": len(padron.registros) if padron else 0})
        return info

    # --- Certificado de ARCA --------------------------------------------
    def _herramientas(self) -> tuple[Certificados, Cifrador]:
        if self.cifrador is None or self.certificados is None:
            raise FaltaClaveServidor("Falta configurar SJ_CLAVE_PARAMETROS en el servidor.")
        return self.certificados, self.cifrador

    def _acceso(self, p: Parametros, descifrar: bool = True) -> tuple[AccesoARCA | None, str]:
        credencial = self.repo.credenciales.get(f"activa:{p.ambiente}")
        if credencial is None:
            return None, f"Falta cargar en Parámetros el certificado de ARCA para {AMBIENTES[p.ambiente].lower()}."
        if credencial.cuit != p.cuit_representante:
            return None, "El certificado cargado es de otro CUIT: generá uno nuevo en Parámetros."
        if credencial.vence is not None and credencial.vence <= self._reloj():
            return None, "El certificado de ARCA venció: generá uno nuevo en Parámetros."
        if self.cifrador is None:
            return None, "Falta configurar la clave del servidor para usar el certificado."
        if not descifrar:
            return AccesoARCA(p.ambiente, credencial.certificado_pem, ""), ""
        return AccesoARCA(p.ambiente, credencial.certificado_pem,
                          self.cifrador.descifrar(credencial.clave_cifrada)), ""

    def estado_certificado(self) -> dict[str, Any]:
        """Sólo datos para mostrar: la clave privada nunca sale de acá."""
        p = self.parametros()
        activa = self.repo.credenciales.get(f"activa:{p.ambiente}")
        pendiente = self.repo.credenciales.get(f"pendiente:{p.ambiente}")
        return {
            "ambiente": p.ambiente, "ambiente_nombre": AMBIENTES[p.ambiente], "cuit": p.cuit_representante,
            "servidor_listo": self.cifrador is not None and self.certificados is not None,
            "activo": None if activa is None else {
                "cuit": activa.cuit, "alias": activa.alias, "sujeto": activa.sujeto, "vence": activa.vence,
                "vencido": activa.vence is not None and activa.vence <= self._reloj(),
                "cargado_por": activa.cargado_por, "cargado_en": activa.cargado_en,
            },
            "pedido": None if pendiente is None else {
                "cuit": pendiente.cuit, "alias": pendiente.alias, "pedido_por": pendiente.pedido_por,
                "pedido_en": pendiente.pedido_en,
            },
        }

    def generar_pedido(self, actor: str) -> str:
        """Genera la clave privada en el servidor (queda cifrada) y devuelve sólo el pedido (CSR)."""
        certificados, cifrador = self._herramientas()
        p = self.parametros()
        alias = "suitejuviar" if p.ambiente == "produccion" else "suitejuviarhomo"
        clave, csr = certificados.generar_pedido(p.cuit_representante, alias, "Suite Juviar")
        self.repo.credenciales[f"pendiente:{p.ambiente}"] = Credencial(
            p.cuit_representante, alias, cifrador.cifrar(clave), csr, actor, self._reloj())
        return csr

    def pedido(self) -> tuple[str, str]:
        p = self.parametros()
        pendiente = self.repo.credenciales.get(f"pendiente:{p.ambiente}")
        if pendiente is None:
            raise LookupError("No hay un pedido de certificado generado.")
        return f"pedido_{pendiente.alias}_{pendiente.cuit}.csr", pendiente.csr_pem

    def cargar_certificado(self, certificado_pem: str, actor: str) -> dict[str, Any]:
        certificados, cifrador = self._herramientas()
        p = self.parametros()
        if "BEGIN CERTIFICATE" not in certificado_pem or len(certificado_pem) > 20000:
            raise ValueError("Subí el archivo .crt (o .pem) que te dio ARCA.")
        if "PRIVATE KEY" in certificado_pem:
            raise ValueError("Ese archivo trae una clave privada: no la subas. Subí sólo el certificado de ARCA.")
        error = "El certificado no corresponde al último pedido generado en Gestión."
        for clave in (f"pendiente:{p.ambiente}", f"activa:{p.ambiente}"):
            credencial = self.repo.credenciales.get(clave)
            if credencial is None:
                continue
            try:
                datos = certificados.leer_certificado(certificado_pem, cifrador.descifrar(credencial.clave_cifrada))
            except ValueError as exc:
                error = str(exc)
                continue
            if datos.cuit != credencial.cuit:
                raise ValueError(f"El certificado es del CUIT {datos.cuit or 'desconocido'}, "
                                 f"no del representante {credencial.cuit}.")
            if datos.vence <= self._reloj():
                raise ValueError("El certificado ya está vencido.")
            self.repo.credenciales[f"activa:{p.ambiente}"] = replace(
                credencial, certificado_pem=certificado_pem.strip(), sujeto=datos.sujeto, vence=datos.vence,
                cargado_por=actor, cargado_en=self._reloj())
            if clave.startswith("pendiente"):
                del self.repo.credenciales[clave]
            return self.estado_certificado()
        raise ValueError(error)
