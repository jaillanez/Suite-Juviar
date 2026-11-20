"""Cliente mínimo de la API BSP de Chattigo."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

from .chattigo_media import cuerpo_documento, cuerpo_imagen

VIGENCIA_SEGUNDOS = 7 * 3600 + 30 * 60


class ErrorChattigo(RuntimeError):
    pass


@dataclass(frozen=True)
class ConfigChattigo:
    base_url: str
    usuario: str
    clave: str
    did: str
    version: str = "v15.0"
    prefijo_auth: str = ""

    @classmethod
    def desde_entorno(cls) -> ConfigChattigo:
        def requerida(nombre: str) -> str:
            valor = os.environ.get(nombre, "").strip()
            if not valor:
                raise RuntimeError(f"Falta la variable de entorno {nombre}")
            return valor

        return cls(
            base_url=requerida("CHATTIGO_BASE_URL").rstrip("/"),
            usuario=requerida("CHATTIGO_USUARIO"),
            clave=requerida("CHATTIGO_CLAVE"),
            did=requerida("CHATTIGO_DID"),
            version=os.environ.get("CHATTIGO_VERSION", "v15.0"),
            prefijo_auth=os.environ.get("CHATTIGO_AUTH_PREFIJO", ""),
        )


MAXIMO_FOTO = 3_000_000
# Donde Meta deja las fotos que mandan los usuarios.
HOSTS_FOTOS = (".fbsbx.com", ".whatsapp.net", ".fbcdn.net")


class ClienteChattigo:
    def __init__(self, config: ConfigChattigo, cliente: httpx.Client | None = None) -> None:
        self._config = config
        self._cliente = cliente or httpx.Client(timeout=15)
        self._token: str | None = None
        self._vence = 0.0

    def _login(self) -> str:
        respuesta = self._cliente.post(
            f"{self._config.base_url}/login",
            json={"username": self._config.usuario, "password": self._config.clave},
        )
        if respuesta.status_code != 200:
            raise ErrorChattigo(f"login falló: HTTP {respuesta.status_code}")
        try:
            token = (respuesta.json() or {}).get("access_token")
        except ValueError as exc:
            raise ErrorChattigo("login devolvió una respuesta inválida") from exc
        if not token:
            raise ErrorChattigo("login sin access_token")
        self._token = token
        self._vence = time.monotonic() + VIGENCIA_SEGUNDOS
        return token

    def _cabeceras(self) -> dict[str, str]:
        token = self._token if self._token and time.monotonic() < self._vence else self._login()
        return {"Authorization": f"{self._config.prefijo_auth}{token}"}

    def _enviar(self, metodo: str, ruta: str, cuerpo: dict | None) -> httpx.Response:
        url = f"{self._config.base_url}{ruta}"
        respuesta = self._cliente.request(
            metodo, url, json=cuerpo, headers=self._cabeceras()
        )
        if respuesta.status_code == 401:
            self._token = None
            respuesta = self._cliente.request(
                metodo, url, json=cuerpo, headers=self._cabeceras()
            )
        if respuesta.status_code >= 400:
            raise ErrorChattigo(
                f"{metodo} {ruta}: HTTP {respuesta.status_code} {respuesta.text[:300]}"
            )
        return respuesta

    def enviar_texto(self, telefono: str, texto: str) -> str:
        respuesta = self._enviar(
            "POST",
            f"/{self._config.version}/{self._config.did}/messages",
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefono,
                "type": "text",
                "text": {"preview_url": False, "body": texto},
            },
        )
        try:
            mensajes = (respuesta.json() or {}).get("messages") or [{}]
        except ValueError as exc:
            raise ErrorChattigo("envío devolvió una respuesta inválida") from exc
        return mensajes[0].get("id", "")

    def _enviar_mensaje(self, cuerpo: dict) -> str:
        respuesta = self._enviar(
            "POST", f"/{self._config.version}/{self._config.did}/messages", cuerpo
        )
        try:
            mensajes = (respuesta.json() or {}).get("messages") or [{}]
        except ValueError as exc:
            raise ErrorChattigo("envío devolvió una respuesta inválida") from exc
        return mensajes[0].get("id", "")

    def enviar_imagen(self, telefono: str, url: str, epigrafe: str | None = None) -> str:
        return self._enviar_mensaje(cuerpo_imagen(telefono, url, epigrafe))

    def enviar_documento(
        self, telefono: str, url: str, nombre: str, epigrafe: str | None = None
    ) -> str:
        return self._enviar_mensaje(cuerpo_documento(telefono, url, nombre, epigrafe))

    def descargar_media(self, media_id: str, maximo: int = MAXIMO_FOTO) -> tuple[bytes, str]:
        """Foto que mandó un usuario: igual que en Meta, primero la dirección y después el archivo."""
        datos = self._enviar("GET", f"/{self._config.version}/{media_id}", None)
        try:
            info = datos.json() or {}
        except ValueError as exc:
            raise ErrorChattigo("la foto devolvió una respuesta inválida") from exc
        url, tipo = str(info.get("url") or ""), str(info.get("mime_type") or "")
        if not self._direccion_de_fotos(url):
            raise ErrorChattigo("la foto no trajo una dirección de Chattigo o de WhatsApp")
        # Meta informa el tamaño antes de bajarlo: lo que se pasa del tope ni se baja.
        if str(info.get("file_size") or "").isdigit() and int(info["file_size"]) > maximo:
            raise ErrorChattigo("el archivo es demasiado grande")
        contenido = bytearray()
        with self._cliente.stream("GET", url, headers=self._cabeceras(), follow_redirects=False) as archivo:
            if archivo.status_code >= 400:
                raise ErrorChattigo(f"no se pudo bajar la foto: HTTP {archivo.status_code}")
            for parte in archivo.iter_bytes():
                contenido.extend(parte)
                if len(contenido) > maximo:
                    raise ErrorChattigo("el archivo es demasiado grande")
            tipo = tipo or archivo.headers.get("content-type", "")
        return bytes(contenido), tipo.split(";")[0]

    def _direccion_de_fotos(self, url: str) -> bool:
        """Sólo https, puerto estándar, sin usuario, y al servidor de Chattigo o a los de WhatsApp."""
        try:
            partes = httpx.URL(url)
        except (httpx.InvalidURL, ValueError):
            return False
        host = partes.host.lower()
        propio = httpx.URL(self._config.base_url).host.lower()
        return (partes.scheme == "https" and partes.port in (None, 443) and not partes.userinfo
                and (host == propio or host.endswith(HOSTS_FOTOS)))

    def configurar_webhook(self, url_webhook: str) -> dict:
        if not url_webhook.startswith("https://"):
            raise ValueError("el webhook tiene que ser HTTPS")
        return self._enviar(
            "PATCH",
            "/webhooks/inbound",
            {"waId": self._config.did, "externalWebhook": url_webhook},
        ).json()
