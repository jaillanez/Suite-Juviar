from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from uuid import uuid4

from ..domain.modelos import (
    AccesoSaludDenegado,
    AdjuntoSalud,
    CertificadoMedico,
    ConsultaAuditoria,
    ReporteNominadoProhibido,
)
from ..domain.puertos import (
    CatalogoDiagnostico,
    FuenteLaboralArticulo208,
    RepositorioAdjuntosSalud,
    RepositorioSalud,
)


class GestionarSalud:
    ROLES_LECTURA = frozenset({"MEDICO"})

    def __init__(self, catalogo: CatalogoDiagnostico, repositorio: RepositorioSalud,
                 adjuntos: RepositorioAdjuntosSalud, fuente_laboral: FuenteLaboralArticulo208):
        self.catalogo = catalogo
        self.repositorio = repositorio
        self.adjuntos = adjuntos
        self.fuente_laboral = fuente_laboral

    def cargar(self, legajo: str, diagnostico_codigo: str, desde: date, hasta: date,
               dias: int, profesional: str, nombre_adjunto: str, contenido_adjunto: bytes) -> CertificadoMedico:
        if self.catalogo.obtener(diagnostico_codigo) is None:
            raise ValueError("El diagnóstico debe elegirse del catálogo médico.")
        if hasta < desde:
            raise ValueError("La fecha hasta no puede ser anterior a la fecha desde.")
        calculados = (hasta - desde).days + 1
        if dias != calculados:
            raise ValueError(f"Los días deben coincidir con las fechas: {calculados}.")
        if not profesional.strip() or not contenido_adjunto:
            raise ValueError("El profesional y el escaneo adjunto son obligatorios.")
        adjunto = AdjuntoSalud(str(uuid4()), nombre_adjunto, bytes(contenido_adjunto))
        self.adjuntos.guardar(adjunto)
        certificado = CertificadoMedico(
            str(uuid4()), legajo, diagnostico_codigo, desde, hasta, dias,
            profesional.strip(), adjunto.id,
        )
        self.repositorio.guardar(certificado)
        return certificado

    def consultar(self, certificado_id: str, actor: str, rol: str | None) -> CertificadoMedico:
        if not rol or rol not in self.ROLES_LECTURA:
            raise AccesoSaludDenegado("El diagnóstico requiere el rol médico.")
        certificado = self.repositorio.obtener(certificado_id)
        if certificado is None:
            raise LookupError("Certificado inexistente.")
        self.auditar(actor, certificado.legajo, "CONSULTA_CERTIFICADO")
        return certificado

    def listar_certificados(self, actor: str, *, legajo: str | None = None,
                            desde: date | None = None, hasta: date | None = None):
        filas = [c for c in self.repositorio.listar()
                 if (not legajo or c.legajo == legajo)
                 and (not desde or c.hasta >= desde) and (not hasta or c.desde <= hasta)]
        self.auditar(actor, legajo, "LISTADO_CERTIFICADOS")
        return filas

    def reporte_agregado(self, incluir_personas: bool = False) -> dict[str, object]:
        if incluir_personas:
            raise ReporteNominadoProhibido("Los reportes de salud nunca son nominados.")
        por_diagnostico: dict[str, set[str]] = defaultdict(set)
        por_estacion: dict[str, set[str]] = defaultdict(set)
        for c in self.repositorio.listar():
            por_diagnostico[c.diagnostico_codigo].add(c.legajo)
            por_estacion[self._estacion(c.desde.month)].add(c.legajo)
        return {
            "por_diagnostico": [
                {"codigo": codigo, "descripcion": self.catalogo.obtener(codigo).descripcion,
                 "personas": len(personas)}
                for codigo, personas in sorted(por_diagnostico.items()) if len(personas) >= 2
            ],
            "por_estacion": [
                {"estacion": estacion, "personas": len(personas)}
                for estacion, personas in sorted(por_estacion.items()) if len(personas) >= 2
            ],
            "grupos_suprimidos": sum(len(p) < 2 for p in por_diagnostico.values())
                + sum(len(p) < 2 for p in por_estacion.values()),
            "minimo_agregado": 2,
            "nominado": False,
        }

    def aviso_articulo_208(self, legajo: str):
        datos = self.fuente_laboral.obtener(legajo)
        if datos is None:
            raise LookupError("El legajo no existe en la fuente laboral.")
        antiguedad_dias, cargas_familia = datos
        aplica = antiguedad_dias >= 365 and cargas_familia > 0
        preliminar = self.fuente_laboral.simulada
        return {"aplica": aplica, "estado": "PRELIMINAR" if preliminar else "DEFINITIVO",
                "preliminar": preliminar, "leyenda": (
                    "Preliminar: antigüedad y cargas de familia simuladas, sin conexión a Nexus"
                    if preliminar else "Datos laborales verificados en Nexus"),
                "imprimible": not preliminar, "exportable": not preliminar}

    def auditar(self, actor: str, legajo: str | None, accion: str) -> None:
        self.repositorio.auditar(ConsultaAuditoria(
            str(uuid4()), actor, datetime.now(UTC), legajo, accion
        ))

    def bitacora(self, actor: str, *, usuario: str | None = None,
                 legajo: str | None = None, desde: date | None = None, hasta: date | None = None):
        filas = [x for x in self.repositorio.listar_auditoria()
                 if (not usuario or x.actor == usuario) and (not legajo or x.legajo == legajo)
                 and (not desde or x.momento.date() >= desde) and (not hasta or x.momento.date() <= hasta)]
        self.auditar(actor, legajo, "CONSULTA_BITACORA")
        return filas

    @staticmethod
    def _estacion(mes: int) -> str:
        if mes in {12, 1, 2}:
            return "VERANO"
        if mes in {3, 4, 5}:
            return "OTOÑO"
        if mes in {6, 7, 8}:
            return "INVIERNO"
        return "PRIMAVERA"
