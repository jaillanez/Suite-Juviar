"""Cliente directo de WhatsApp Cloud API de Meta (sin intermediario).

Mismos mensajes que ya se mandaban por Chattigo (el formato es el de Meta);
cambia a dónde van y cómo se autentican: token permanente de un usuario del
sistema en el Administrador comercial de Meta.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import httpx

from .botones import cuerpo_opciones, partir_cuerpo
from .chattigo import ErrorChattigo
from .chattigo_media import cuerpo_documento, cuerpo_imagen

GRAPH = "https://graph.facebook.com"
MAXIMO_FOTO = 3_000_000
# Donde Meta deja las fotos que mandan los usuarios.
HOSTS_FOTOS = (".fbsbx.com", ".whatsapp.net", ".fbcdn.net")


class ErrorMeta(ErrorChattigo):
    """Falla del canal: el worker la trata igual que las de Chattigo (reintenta)."""

    def __init__(self, mensaje: str, codigo: int | None = None) -> None:
        super().__init__(mensaje)
        self.codigo = codigo


class ErrorPlantilla(ErrorMeta):
    """Meta no acepta la plantilla (no existe en ese idioma, no está aprobada, está pausada o
    los parámetros no coinciden): errores 132000 a 132999 de Cloud API. El aviso puede salir
    como texto, que llega si la persona escribió en las últimas 24 h."""


def _codigo_error(respuesta: httpx.Response) -> int | None:
    try:
        codigo = ((respuesta.json() or {}).get("error") or {}).get("code")
    except (ValueError, AttributeError):
        return None
    return codigo if isinstance(codigo, int) else None


@dataclass(frozen=True)
class ConfigMeta:
    token: str
    numero_id: str  # «Identificador del número de teléfono» en Meta
    version: str = "v23.0"
    cuenta_id: str = ""  # «Identificador de la cuenta de WhatsApp Business», para suscribir

    @classmethod
    def desde_entorno(cls) -> ConfigMeta:
        def requerida(nombre: str) -> str:
            valor = os.environ.get(nombre, "").strip()
            if not valor:
                raise RuntimeError(f"Falta la variable de entorno {nombre}")
            return valor

        return cls(
            token=requerida("META_TOKEN"),
            numero_id=requerida("META_NUMERO_ID"),
            version=os.environ.get("META_VERSION", "").strip() or "v23.0",
            cuenta_id=os.environ.get("META_CUENTA_ID", "").strip(),
        )


class ClienteMeta:
    def __init__(self, config: ConfigMeta, cliente: httpx.Client | None = None) -> None:
        self._config = config
        self._cliente = cliente or httpx.Client(timeout=15)

    def _cabeceras(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._config.token}"}

    def _pedir(self, metodo: str, ruta: str, cuerpo: dict | None = None) -> httpx.Response:
        respuesta = self._cliente.request(
            metodo, f"{GRAPH}/{self._config.version}{ruta}", json=cuerpo, headers=self._cabeceras()
        )
        if respuesta.status_code >= 400:
            codigo = _codigo_error(respuesta)
            clase = ErrorPlantilla if codigo is not None and 132000 <= codigo <= 132999 else ErrorMeta
            raise clase(f"{metodo} {ruta}: HTTP {respuesta.status_code} {respuesta.text[:300]}", codigo)
        return respuesta

    def _enviar_mensaje(self, cuerpo: dict) -> str:
        respuesta = self._pedir("POST", f"/{self._config.numero_id}/messages", cuerpo)
        try:
            mensajes = (respuesta.json() or {}).get("messages") or [{}]
        except ValueError as exc:
            raise ErrorMeta("envío devolvió una respuesta inválida") from exc
        return mensajes[0].get("id", "")

    def enviar_texto(self, telefono: str, texto: str) -> str:
        return self._enviar_mensaje({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefono,
            "type": "text",
            "text": {"preview_url": False, "body": texto},
        })

    def enviar_opciones(self, telefono: str, texto: str, opciones: list[str], desde: int = 0) -> str:
        """Botones (hasta 3 opciones) o lista (más): ver botones.py. Si el texto no entra como
        cuerpo, lo largo sale antes como texto común."""
        antes, cuerpo = partir_cuerpo(texto)
        if antes:
            self.enviar_texto(telefono, antes)
        return self._enviar_mensaje(cuerpo_opciones(telefono, cuerpo, opciones, desde))

    def enviar_plantilla(self, telefono: str, nombre: str, idioma: str, parametros: list[str]) -> str:
        """Plantilla aprobada (sale aunque la persona no haya escrito en las últimas 24 h)."""
        plantilla: dict = {"name": nombre, "language": {"code": idioma}}
        if parametros:
            plantilla["components"] = [{
                "type": "body",
                "parameters": [{"type": "text", "text": valor} for valor in parametros],
            }]
        return self._enviar_mensaje({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefono,
            "type": "template",
            "template": plantilla,
        })

    def enviar_imagen(self, telefono: str, url: str, epigrafe: str | None = None) -> str:
        return self._enviar_mensaje(cuerpo_imagen(telefono, url, epigrafe))

    def enviar_documento(
        self, telefono: str, url: str, nombre: str, epigrafe: str | None = None
    ) -> str:
        return self._enviar_mensaje(cuerpo_documento(telefono, url, nombre, epigrafe))

    def descargar_media(self, media_id: str, maximo: int = MAXIMO_FOTO) -> tuple[bytes, str]:
        """Foto que mandó un usuario: primero se pide la dirección y después el archivo."""
        try:
            info = self._pedir("GET", f"/{media_id}").json() or {}
        except ValueError as exc:
            raise ErrorMeta("la foto devolvió una respuesta inválida") from exc
        url, tipo = str(info.get("url") or ""), str(info.get("mime_type") or "")
        if not _direccion_de_fotos(url):
            raise ErrorMeta("la foto no trajo una dirección de WhatsApp")
        # Meta informa el tamaño antes de bajarlo: lo que se pasa del tope ni se baja.
        if str(info.get("file_size") or "").isdigit() and int(info["file_size"]) > maximo:
            raise ErrorMeta("el archivo es demasiado grande")
        contenido = bytearray()
        with self._cliente.stream("GET", url, headers=self._cabeceras(),
                                  follow_redirects=False) as archivo:
            if archivo.status_code >= 400:
                raise ErrorMeta(f"no se pudo bajar la foto: HTTP {archivo.status_code}")
            for parte in archivo.iter_bytes():
                contenido.extend(parte)
                if len(contenido) > maximo:
                    raise ErrorMeta("el archivo es demasiado grande")
            tipo = tipo or archivo.headers.get("content-type", "")
        return bytes(contenido), tipo.split(";")[0]

    def suscribir_cuenta(self) -> dict:
        """Hace que la cuenta de WhatsApp Business mande sus mensajes a esta app."""
        if not self._config.cuenta_id:
            raise RuntimeError("Falta la variable de entorno META_CUENTA_ID")
        return self._pedir("POST", f"/{self._config.cuenta_id}/subscribed_apps").json()

    def _cuenta(self) -> str:
        if not self._config.cuenta_id:
            raise RuntimeError("Falta la variable de entorno META_CUENTA_ID")
        return self._config.cuenta_id

    def plantillas(self, nombre: str | None = None) -> list[dict]:
        """Plantillas de la cuenta (con su estado de aprobación); con nombre, sólo esa."""
        consulta = "fields=name,language,status,category,rejected_reason&limit=100"
        if nombre:
            # Los nombres de plantilla de Meta son minúsculas, números y guion bajo.
            if not re.fullmatch(r"[a-z0-9_]{1,512}", nombre):
                raise ValueError("nombre de plantilla inválido")
            consulta += f"&name={nombre}"
        try:
            datos = self._pedir("GET", f"/{self._cuenta()}/message_templates?{consulta}").json() or {}
        except ValueError as exc:
            raise ErrorMeta("la lista de plantillas devolvió una respuesta inválida") from exc
        return [p for p in datos.get("data") or [] if not nombre or p.get("name") == nombre]

    def crear_plantilla(self, cuerpo: dict) -> dict:
        """Manda una plantilla a revisión de Meta."""
        try:
            return self._pedir("POST", f"/{self._cuenta()}/message_templates", cuerpo).json() or {}
        except ValueError as exc:
            raise ErrorMeta("la plantilla devolvió una respuesta inválida") from exc


def _direccion_de_fotos(url: str) -> bool:
    """Sólo https, puerto estándar, sin usuario, y a los servidores de WhatsApp."""
    try:
        partes = httpx.URL(url)
    except (httpx.InvalidURL, ValueError):
        return False
    return (partes.scheme == "https" and partes.port in (None, 443) and not partes.userinfo
            and partes.host.lower().endswith(HOSTS_FOTOS))
