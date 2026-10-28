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

    def _enviar(self, metodo: str, ruta: str, cuerpo: dict) -> httpx.Response:
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

    def configurar_webhook(self, url_webhook: str) -> dict:
        if not url_webhook.startswith("https://"):
            raise ValueError("el webhook tiene que ser HTTPS")
        return self._enviar(
            "PATCH",
            "/webhooks/inbound",
            {"waId": self._config.did, "externalWebhook": url_webhook},
        ).json()
