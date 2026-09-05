"""Composition root: entrega de EPP con constancia firmada.

Este flujo toca tres cosas que no se conocen entre sí:

  * identidad  — el nombre, DNI y puesto de la cabecera del RD 062/11 se traen
                 de Nexus, no se tipean (§3.1).
  * rrhh_epp   — la constancia y los ítems del catálogo RD 068/11.
  * firma      — el motor compartido de la plataforma (§5.3).

Ninguno de los tres importa a los otros. El único lugar autorizado a conocerlos
a la vez es este archivo.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from suite_juviar.modulos.rrhh_epp.domain.entidades import ConstanciaEntrega, ItemEntregado
from suite_juviar.modulos.rrhh_epp.domain.puertos import CatalogoEPP, RepositorioConstancias
from suite_juviar.plataforma.bitacora.domain.entidades import Actor, AsientoBitacora, TipoActor
from suite_juviar.plataforma.bitacora.domain.puertos import Bitacora
from suite_juviar.plataforma.firma.domain.entidades import (
    DocumentoFirmado,
    MetodoFirmaElectronica,
)
from suite_juviar.plataforma.firma.domain.puertos import MotorDeFirma, RepositorioDocumentos
from suite_juviar.plataforma.identidad.domain.entidades import NumeroLegajo
from suite_juviar.plataforma.identidad.domain.puertos import RepositorioLegajos


class RegistrarEntregaEPP:
    def __init__(
        self,
        legajos: RepositorioLegajos,
        catalogo: CatalogoEPP,
        constancias: RepositorioConstancias,
        firma: MotorDeFirma,
        documentos: RepositorioDocumentos,
        bitacora: Bitacora,
        generar_pdf,
    ) -> None:
        self._legajos = legajos
        self._catalogo = catalogo
        self._constancias = constancias
        self._firma = firma
        self._documentos = documentos
        self._bitacora = bitacora
        self._generar_pdf = generar_pdf

    async def __call__(
        self,
        legajo_receptor: str,
        items: list[ItemEntregado],
        entregado_por_legajo: str,
        metodo_firma: MetodoFirmaElectronica,
        evidencia_firma: bytes,
    ) -> ConstanciaEntrega:
        legajo = await self._legajos.obtener(NumeroLegajo(legajo_receptor))
        if legajo is None or not legajo.activo:
            raise LookupError("El legajo no existe en Nexus o está inactivo")

        for item in items:
            if await self._catalogo.obtener(item.codigo_catalogo) is None:
                raise ValueError(
                    f"Código {item.codigo_catalogo} inexistente en el RD 068/11"
                )

        constancia = ConstanciaEntrega(
            legajo=legajo.numero.valor,
            sector=legajo.sector,
            puesto=legajo.puesto,
            entregado_por_legajo=entregado_por_legajo,
            fecha=datetime.now(UTC).date(),
        )
        for item in items:
            constancia.agregar(item)

        documento_id = uuid4()
        pdf = await self._generar_pdf(constancia, legajo)

        firma_empresa = await self._firma.firmar_como_empresa(
            documento_id, pdf, entregado_por_legajo
        )
        firma_trabajador = await self._firma.firmar_como_trabajador(
            documento_id, pdf, legajo.numero.valor, metodo_firma, evidencia_firma
        )

        await self._documentos.guardar(
            DocumentoFirmado(
                id=documento_id,
                tipo_documento="constancia_epp",
                contenido=pdf,
                hash_sha256=firma_empresa.hash_documento,
                firmas=(firma_empresa, firma_trabajador),
            )
        )
        constancia.firmar(documento_id)
        await self._constancias.guardar(constancia)
        await self._bitacora.registrar(
            AsientoBitacora(
                accion="epp.entrega.firmada",
                actor=Actor(TipoActor.EMPLEADO, entregado_por_legajo),
                entidad="constancia_epp",
                entidad_id=str(constancia.id),
                modulo="rrhh_epp",
                datos={"legajo_receptor": legajo.numero.valor, "items": len(items)},
            )
        )
        return constancia
