from __future__ import annotations

import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..domain.modelos import AdjuntoSalud, CertificadoMedico, ConsultaAuditoria, Diagnostico


class CatalogoDiagnosticoSimulado:
    simulada = True
    dueno_dato = "Servicio Médico"

    def __init__(self):
        self._datos = {
            "MUESTRA": Diagnostico("MUESTRA", "Catálogo de demostración", None),
            "MUESTRA-RESP": Diagnostico("MUESTRA-RESP", "Afección respiratoria (muestra)", "MUESTRA"),
            "MUESTRA-TRAU": Diagnostico("MUESTRA-TRAU", "Traumatismo (muestra)", "MUESTRA"),
        }

    def obtener(self, codigo: str) -> Diagnostico | None:
        return self._datos.get(codigo)

    def listar(self) -> list[Diagnostico]:
        return list(self._datos.values())


class SaludMemoria:
    def __init__(self):
        self.certificados: dict[str, CertificadoMedico] = {}
        self.consultas: list[ConsultaAuditoria] = []

    def guardar(self, certificado: CertificadoMedico) -> None:
        self.certificados[certificado.id] = certificado

    def obtener(self, certificado_id: str) -> CertificadoMedico | None:
        return self.certificados.get(certificado_id)

    def listar(self) -> list[CertificadoMedico]:
        return list(self.certificados.values())

    def auditar(self, consulta: ConsultaAuditoria) -> None:
        self.consultas.append(consulta)

    def listar_auditoria(self) -> list[ConsultaAuditoria]:
        return list(self.consultas)


class AdjuntosSaludCifradosMemoria:
    def __init__(self, clave: bytes):
        self._aes = AESGCM(clave)
        self._filas: dict[str, tuple[bytes, bytes]] = {}

    def guardar(self, adjunto: AdjuntoSalud) -> None:
        nonce = os.urandom(12)
        cabecera = json.dumps({"id": adjunto.id, "nombre": adjunto.nombre}).encode()
        self._filas[adjunto.id] = (nonce, self._aes.encrypt(nonce, cabecera + b"\0" + adjunto.contenido, b"salud-adjunto"))

    def obtener(self, adjunto_id: str) -> AdjuntoSalud | None:
        fila = self._filas.get(adjunto_id)
        if fila is None:
            return None
        plano = self._aes.decrypt(fila[0], fila[1], b"salud-adjunto")
        cabecera, contenido = plano.split(b"\0", 1)
        datos = json.loads(cabecera)
        return AdjuntoSalud(datos["id"], datos["nombre"], contenido)

    def bytes_persistidos(self, adjunto_id: str) -> bytes:
        return self._filas[adjunto_id][1]


class FuenteLaboralSimulada:
    simulada = True

    def __init__(self, datos: dict[str, tuple[int, int]] | None = None):
        self._datos = datos or {"1042": (500, 1), "10": (500, 1)}

    def obtener(self, legajo: str) -> tuple[int, int] | None:
        return self._datos.get(legajo)
