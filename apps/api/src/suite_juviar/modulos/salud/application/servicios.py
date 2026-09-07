from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from uuid import uuid4

from ..domain.modelos import (
    AccesoSaludDenegado,
    CertificadoMedico,
    ConsultaAuditoria,
    ReporteNominadoProhibido,
)
from ..domain.puertos import CatalogoDiagnostico, RepositorioSalud


class GestionarSalud:
    ROLES_LECTURA = frozenset({"MEDICO"})

    def __init__(self, catalogo: CatalogoDiagnostico, repositorio: RepositorioSalud):
        self.catalogo = catalogo
        self.repositorio = repositorio

    def cargar(self, legajo: str, diagnostico_codigo: str, desde: date, hasta: date) -> CertificadoMedico:
        if self.catalogo.obtener(diagnostico_codigo) is None:
            raise ValueError("El diagnóstico debe elegirse del catálogo médico.")
        certificado = CertificadoMedico(str(uuid4()), legajo, diagnostico_codigo, desde, hasta)
        self.repositorio.guardar(certificado)
        return certificado

    def consultar(self, certificado_id: str, actor: str, rol: str | None) -> CertificadoMedico:
        if not rol or rol not in self.ROLES_LECTURA:
            raise AccesoSaludDenegado("El diagnóstico requiere el rol médico.")
        certificado = self.repositorio.obtener(certificado_id)
        if certificado is None:
            raise LookupError("Certificado inexistente.")
        self.repositorio.auditar(ConsultaAuditoria(certificado.id, actor, datetime.now(UTC)))
        return certificado

    def reporte_agregado(self, incluir_personas: bool = False) -> dict[str, object]:
        if incluir_personas:
            raise ReporteNominadoProhibido("Los reportes de salud nunca son nominados.")
        conteo = Counter(c.diagnostico_codigo for c in self.repositorio.listar())
        por_mes = Counter(c.desde.month for c in self.repositorio.listar())
        return {
            "por_enfermedad": dict(conteo),
            "estacionalidad_por_mes": dict(por_mes),
            "nominado": False,
        }

    def aviso_articulo_208(self, antiguedad_dias: int, cargas_familia: int, fuente_simulada: bool):
        aplica = antiguedad_dias >= 365 and cargas_familia > 0
        return {"aplica": aplica, "estado": "PRELIMINAR" if fuente_simulada else "DEFINITIVO"}
