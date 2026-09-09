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

    def buscar(self, *, apellido=None, legajo=None, sector=None, empresa=None):
        return _filtrar(self._personas.values(), apellido, legajo, sector, empresa)


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

    def buscar(self, *, apellido=None, legajo=None, sector=None, empresa=None):
        personas = self._fuente.listar_activos()
        proyectadas = [
            PersonaLegajo(p.legajo, p.nombre_completo, p.empresa, p.sector, p.puesto)
            for p in personas
        ]
        return _filtrar(proyectadas, apellido, legajo, sector, empresa)


def _filtrar(personas, apellido, legajo, sector, empresa):
    def contiene(valor: str, filtro: str | None) -> bool:
        return not filtro or filtro.casefold() in valor.casefold()
    return sorted([
        p for p in personas
        if contiene(p.nombre_completo, apellido) and contiene(p.legajo, legajo)
        and contiene(p.sector, sector) and contiene(p.empresa, empresa)
    ], key=lambda p: (p.nombre_completo, p.legajo))


class AdjuntosCifradosMemoria:
    def __init__(self, clave: bytes):
        if len(clave) not in {16, 24, 32}:
            raise ValueError("La clave AES debe tener 16, 24 o 32 bytes.")
        self._aes = AESGCM(clave)
        self._filas: dict[str, tuple[bytes, bytes]] = {}

    def guardar(self, adjunto: Adjunto) -> None:
        nonce = os.urandom(12)
        plano = json.dumps(
            {"id": adjunto.id, "legajo": adjunto.legajo, "nombre": adjunto.nombre,
             "activo": adjunto.activo, "dado_baja_por": adjunto.dado_baja_por,
             "dado_baja_en": adjunto.dado_baja_en.isoformat() if adjunto.dado_baja_en else None,
             "motivo_baja": adjunto.motivo_baja}
        ).encode() + b"\0" + adjunto.contenido
        self._filas[adjunto.id] = (nonce, self._aes.encrypt(nonce, plano, b"legajo-adjunto"))

    def obtener(self, adjunto_id: str) -> Adjunto | None:
        fila = self._filas.get(adjunto_id)
        if fila is None:
            return None
        cabecera, contenido = self._aes.decrypt(fila[0], fila[1], b"legajo-adjunto").split(b"\0", 1)
        datos = json.loads(cabecera)
        from datetime import datetime
        return Adjunto(datos["id"], datos["legajo"], datos["nombre"], contenido,
                       datos.get("activo", True), datos.get("dado_baja_por"),
                       datetime.fromisoformat(datos["dado_baja_en"]) if datos.get("dado_baja_en") else None,
                       datos.get("motivo_baja"))

    def listar(self, legajo: str, incluir_bajas: bool = True) -> list[Adjunto]:
        adjuntos = [self.obtener(i) for i in self._filas]
        return [a for a in adjuntos if a and a.legajo == legajo and (incluir_bajas or a.activo)]

    def reemplazar(self, adjunto: Adjunto) -> None:
        if adjunto.id not in self._filas:
            raise LookupError("Adjunto inexistente")
        self.guardar(adjunto)

    def bytes_persistidos(self, adjunto_id: str) -> bytes:
        return self._filas[adjunto_id][1]
