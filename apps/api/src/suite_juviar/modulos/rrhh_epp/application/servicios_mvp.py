"""Casos de uso del módulo. Acá vive la regla, no en la pantalla ni en la API."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from ..domain.modelos_mvp import (
    CantidadInvalida,
    CodigoFueraDeCatalogo,
    ElementoEPP,
    Entrega,
    EntregaSinLineas,
    FirmaFaltante,
    Legajo,
    LegajoInactivo,
    LegajoInexistente,
    LineaEntrega,
    MetodoDeFirmaNoHabilitado,
    RequisitoEPP,
)
from ..domain.puertos_mvp import (
    Bitacora,
    MotorFirma,
    RepositorioCatalogo,
    RepositorioEntregas,
    RepositorioLegajos,
)


class ConsultarLegajo:
    """Devuelve la cabecera del RD 062/11 y su EPP por sector + puesto."""

    def __init__(self, legajos: RepositorioLegajos, catalogo: RepositorioCatalogo,
                 entregas: RepositorioEntregas) -> None:
        self._legajos = legajos
        self._catalogo = catalogo
        self._entregas = entregas

    def ejecutar(self, numero: str) -> tuple[Legajo, list[tuple[RequisitoEPP, ElementoEPP]], list[Entrega]]:
        persona = self._legajos.obtener(numero)
        if persona is None:
            raise LegajoInexistente(f"El legajo {numero} no existe en {self._legajos.fuente}.")
        if not persona.activo:
            raise LegajoInactivo(
                f"El legajo {numero} figura dado de baja. No se puede registrar una entrega."
            )

        requeridos: list[tuple[RequisitoEPP, ElementoEPP]] = []
        for requisito in self._catalogo.requisitos_de(
            persona.sector_codigo,
            persona.puesto_codigo,
        ):
            elemento = self._catalogo.obtener_elemento(requisito.codigo)
            if elemento is None:
                # La matriz apunta a un código que no está en el catálogo.
                # Se avisa fuerte: es un error de datos, no del operario.
                raise CodigoFueraDeCatalogo(
                    f"La matriz de {persona.sector_codigo}/{persona.puesto_codigo} pide el código "
                    f"{requisito.codigo}, que no existe en el catálogo RD 068/11."
                )
            requeridos.append((requisito, elemento))

        historial = self._entregas.listar_por_legajo(numero)
        return persona, requeridos, historial


class RegistrarEntrega:
    """Registra una entrega de ropa de trabajo y EPP con conformidad del trabajador."""

    def __init__(
        self,
        legajos: RepositorioLegajos,
        catalogo: RepositorioCatalogo,
        entregas: RepositorioEntregas,
        firma: MotorFirma,
        bitacora: Bitacora,
    ) -> None:
        self._legajos = legajos
        self._catalogo = catalogo
        self._entregas = entregas
        self._firma = firma
        self._bitacora = bitacora

    def ejecutar(
        self,
        numero_legajo: str,
        items: list[dict],
        metodo_firma: str,
        evidencia_firma: str,
        usuario_deposito: str,
        observaciones: str = "",
        fecha: date | None = None,
    ) -> Entrega:
        persona = self._legajos.obtener(numero_legajo)
        if persona is None:
            raise LegajoInexistente(f"El legajo {numero_legajo} no existe en {self._legajos.fuente}.")
        if not persona.activo:
            raise LegajoInactivo(f"El legajo {numero_legajo} figura dado de baja.")

        if not items:
            raise EntregaSinLineas("No se seleccionó ningún elemento para entregar.")

        # Regla 3: todo lo que se entrega sale del catálogo. Nada de texto libre.
        lineas: list[LineaEntrega] = []
        for item in items:
            codigo = str(item.get("codigo", "")).strip()
            elemento = self._catalogo.obtener_elemento(codigo)
            if elemento is None:
                raise CodigoFueraDeCatalogo(
                    f"El código {codigo or '(vacío)'} no existe en el catálogo RD 068/11."
                )
            cantidad = item.get("cantidad")
            if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad <= 0:
                raise CantidadInvalida(
                    f"Cantidad inválida para el código {codigo}: {cantidad!r}."
                )
            lineas.append(
                LineaEntrega(
                    codigo=elemento.codigo,
                    producto=elemento.producto,
                    tipo_modelo=elemento.tipo_modelo,
                    marca=elemento.marca,
                    posee_certificacion=elemento.posee_certificacion,
                    certificacion=elemento.certificacion,
                    cantidad=cantidad,
                )
            )

        # Sin conformidad del trabajador no hay constancia. Es el punto entero
        # de la Disposición SRT 3/2022.
        if not evidencia_firma or not evidencia_firma.strip():
            raise FirmaFaltante("Falta la conformidad del trabajador.")
        if metodo_firma not in self._firma.metodos_habilitados:
            raise MetodoDeFirmaNoHabilitado(
                f"El método de firma '{metodo_firma}' no está habilitado. "
                f"Habilitados: {', '.join(self._firma.metodos_habilitados)}."
            )

        id_entrega = uuid.uuid4().hex[:12].upper()
        documento = {
            "id": id_entrega,
            "legajo": persona.legajo,
            "dni": persona.dni,
            "lineas": [l.__dict__ for l in lineas],
        }
        firma = self._firma.firmar_trabajador(metodo_firma, evidencia_firma, documento)

        entrega = Entrega(
            id=id_entrega,
            legajo=persona,
            lineas=tuple(lineas),
            fecha_entrega=fecha or datetime.now(UTC).date(),
            firma_trabajador=firma,
            usuario_deposito=usuario_deposito,
            observaciones=observaciones,
        )
        self._entregas.guardar(entrega)
        self._bitacora.registrar(
            evento="ENTREGA_EPP_REGISTRADA",
            usuario=usuario_deposito,
            detalle={
                "id_entrega": id_entrega,
                "legajo": persona.legajo,
                "fuente_legajos": self._legajos.fuente,
                "items": len(lineas),
                "metodo_firma": firma.metodo,
                "firma_simulada": firma.simulada,
            },
        )
        return entrega
