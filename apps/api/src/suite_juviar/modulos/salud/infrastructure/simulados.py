from __future__ import annotations

from ..domain.modelos import CertificadoMedico, ConsultaAuditoria, Diagnostico


class CatalogoDiagnosticoSimulado:
    simulada = True
    dueno_dato = "Servicio Médico"

    def __init__(self):
        self._datos = {
            "MUESTRA-RESP": Diagnostico("MUESTRA-RESP", "Afección respiratoria (muestra)"),
            "MUESTRA-TRAU": Diagnostico("MUESTRA-TRAU", "Traumatismo (muestra)"),
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
