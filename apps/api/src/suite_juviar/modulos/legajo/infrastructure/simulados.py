from __future__ import annotations

import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..domain.modelos import Adjunto, PersonaLegajo


class FuenteLegajosSimulada:
    simulada = True

    def __init__(self, personas: list[PersonaLegajo]):
        self._personas = {p.legajo: p for p in personas}

    def obtener(self, legajo: str) -> PersonaLegajo | None:
        return self._personas.get(legajo)


class FuenteLegajosDesdePuerto:
    """Traduce estructuralmente el puerto existente sin importar RRHH/EPP."""

    def __init__(self, fuente_existente):
        self._fuente = fuente_existente

    @property
    def simulada(self) -> bool:
        return self._fuente.fuente != "NEXUS"

    def obtener(self, legajo: str) -> PersonaLegajo | None:
        persona = self._fuente.obtener(legajo)
        if persona is None:
            return None
        return PersonaLegajo(
            legajo=persona.legajo,
            nombre_completo=persona.nombre_completo,
            empresa=persona.empresa,
            sector=persona.sector,
            puesto=persona.puesto,
        )


class AdjuntosCifradosMemoria:
    def __init__(self, clave: bytes):
        if len(clave) not in {16, 24, 32}:
            raise ValueError("La clave AES debe tener 16, 24 o 32 bytes.")
        self._aes = AESGCM(clave)
        self._filas: dict[str, tuple[bytes, bytes]] = {}

    def guardar(self, adjunto: Adjunto) -> None:
        nonce = os.urandom(12)
        plano = json.dumps(
            {"id": adjunto.id, "legajo": adjunto.legajo, "nombre": adjunto.nombre}
        ).encode() + b"\0" + adjunto.contenido
        self._filas[adjunto.id] = (nonce, self._aes.encrypt(nonce, plano, b"legajo-adjunto"))

    def obtener(self, adjunto_id: str) -> Adjunto | None:
        fila = self._filas.get(adjunto_id)
        if fila is None:
            return None
        cabecera, contenido = self._aes.decrypt(fila[0], fila[1], b"legajo-adjunto").split(b"\0", 1)
        datos = json.loads(cabecera)
        return Adjunto(datos["id"], datos["legajo"], datos["nombre"], contenido)

    def bytes_persistidos(self, adjunto_id: str) -> bytes:
        return self._filas[adjunto_id][1]
