"""Envío de imagen y documento por Chattigo (formato Meta Cloud API).

Se agrega al ClienteChattigo que ya existe: mismo login, mismo token, misma
ruta POST /{version}/{did}/messages, cambia el cuerpo.

Meta descarga el enlace desde sus servidores: tiene que ser HTTPS y
alcanzable desde afuera. Por eso el archivo se publica en el dominio del bot
y no en una dirección interna.
"""
from __future__ import annotations


def cuerpo_imagen(telefono: str, url: str, epigrafe: str | None = None) -> dict:
    imagen: dict[str, str] = {"link": url}
    if epigrafe:
        imagen["caption"] = epigrafe[:1024]
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefono,
        "type": "image",
        "image": imagen,
    }


def cuerpo_documento(telefono: str, url: str, nombre: str, epigrafe: str | None = None) -> dict:
    documento: dict[str, str] = {"link": url, "filename": nombre}
    if epigrafe:
        documento["caption"] = epigrafe[:1024]
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefono,
        "type": "document",
        "document": documento,
    }


# --- Para agregar a ClienteChattigo -------------------------------------------
#
#     def enviar_imagen(self, telefono: str, url: str, epigrafe: str | None = None) -> str:
#         return self._enviar_mensaje(cuerpo_imagen(telefono, url, epigrafe))
#
#     def enviar_documento(self, telefono, url, nombre, epigrafe=None) -> str:
#         return self._enviar_mensaje(cuerpo_documento(telefono, url, nombre, epigrafe))
#
# donde _enviar_mensaje es lo que hoy hace enviar_texto después de armar el
# cuerpo: mismo POST, mismo reintento ante 401, misma lectura del wamid.
