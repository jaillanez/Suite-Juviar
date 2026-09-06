"""Casos de uso del módulo. Acá vive la regla, no en la pantalla ni en la API."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from ..domain.modelos_mvp import (
    CantidadInvalida,
    CircuitoEntregaInvalido,
    CodigoFueraDeCatalogo,
    ElementoEPP,
    Entrega,
    EntregaSinLineas,
    FirmaFaltante,
    ItemFueraDeCatalogo,
    Legajo,
    LegajoInactivo,
    LegajoInexistente,
    LineaEntrega,
    MetodoDeFirmaNoHabilitado,
    MotivoReposicionInvalido,
    RequisitoEPP,
)
from ..domain.puertos_mvp import (
    Bitacora,
    MotorFirma,
    RepositorioCatalogo,
    RepositorioEntregas,
    RepositorioLegajos,
    RepositorioStock,
)


class ConsultarLegajo:
    """Devuelve la cabecera del RD 062/11 y su EPP por sector + puesto."""

    def __init__(
        self,
        legajos: RepositorioLegajos,
        catalogo: RepositorioCatalogo,
        entregas: RepositorioEntregas,
    ) -> None:
        self._legajos = legajos
        self._catalogo = catalogo
        self._entregas = entregas

    def ejecutar(
        self, numero: str
    ) -> tuple[Legajo, list[tuple[RequisitoEPP, ElementoEPP]], list[Entrega]]:
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
        stock: RepositorioStock,
    ) -> None:
        self._legajos = legajos
        self._catalogo = catalogo
        self._entregas = entregas
        self._firma = firma
        self._bitacora = bitacora
        self._stock = stock

    def ejecutar(
        self,
        numero_legajo: str,
        items: list[dict],
        metodo_firma: str,
        evidencia_firma: str,
        usuario_deposito: str,
        observaciones: str = "",
        fecha: date | None = None,
        id_entrega: str | None = None,
        entregada_en: datetime | None = None,
        circuito: str = "ESPONTANEA",
        motivo: str = "DESGASTE",
    ) -> Entrega:
        # El identificador nace en la tablet. Si la respuesta se perdió y la cola
        # reintenta, devolvemos el registro existente sin volver a firmar ni auditar.
        id_entrega = id_entrega or uuid.uuid4().hex[:12].upper()
        existente = self._entregas.obtener(id_entrega)
        if existente is not None:
            return existente

        if circuito not in {"PROGRAMADA", "ESPONTANEA"}:
            raise CircuitoEntregaInvalido("El circuito debe ser PROGRAMADA o ESPONTANEA.")
        motivos_habilitados = (
            {"ENTREGA_ESTACIONAL"} if circuito == "PROGRAMADA" else {"ROTURA", "DESGASTE"}
        )
        if motivo not in motivos_habilitados:
            raise MotivoReposicionInvalido(
                f"El motivo {motivo or '(vacío)'} no corresponde al circuito {circuito}."
            )

        persona = self._legajos.obtener(numero_legajo)
        if persona is None:
            raise LegajoInexistente(
                f"El legajo {numero_legajo} no existe en {self._legajos.fuente}."
            )
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
            item_codigo = str(item.get("item_codigo") or "").strip()
            item_catalogo = self._catalogo.obtener_item(item_codigo)
            if item_catalogo is None or item_catalogo.elemento_codigo != codigo:
                raise ItemFueraDeCatalogo(
                    f"El ítem {item_codigo or '(vacío)'} no pertenece al elemento {codigo}."
                )
            cantidad = item.get("cantidad")
            if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad <= 0:
                raise CantidadInvalida(f"Cantidad inválida para el código {codigo}: {cantidad!r}.")
            lineas.append(
                LineaEntrega(
                    codigo=elemento.codigo,
                    producto=elemento.producto,
                    tipo_modelo=item_catalogo.modelo,
                    marca=item_catalogo.marca,
                    posee_certificacion=elemento.posee_certificacion,
                    certificacion=elemento.certificacion,
                    cantidad=cantidad,
                    item_codigo=item_catalogo.codigo_interno,
                    talle=item_catalogo.talle,
                    color=item_catalogo.color,
                    estado_item=item_catalogo.estado,
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

        movimientos_stock = [(linea.item_codigo, linea.cantidad) for linea in lineas]
        self._stock.verificar(movimientos_stock)

        momento_entrega = entregada_en or datetime.now(UTC)
        if momento_entrega.tzinfo is None:
            momento_entrega = momento_entrega.replace(tzinfo=UTC)
        documento = {
            "id": id_entrega,
            "legajo": persona.legajo,
            "dni": persona.dni,
            "lineas": [l.__dict__ for l in lineas],
            "entregada_en": momento_entrega.isoformat(),
            "usuario_deposito": usuario_deposito,
        }
        firma = self._firma.firmar_trabajador(
            metodo_firma,
            evidencia_firma,
            documento,
            sello_tiempo=momento_entrega,
        )

        entrega = Entrega(
            id=id_entrega,
            legajo=persona,
            lineas=tuple(lineas),
            fecha_entrega=fecha or momento_entrega.date(),
            firma_trabajador=firma,
            usuario_deposito=usuario_deposito,
            circuito=circuito,
            motivo=motivo,
            observaciones=observaciones,
        )
        if not self._entregas.guardar(entrega):
            existente = self._entregas.obtener(id_entrega)
            if existente is not None:
                return existente
            raise RuntimeError("La entrega duplicada no pudo recuperarse del repositorio.")
        self._stock.descontar(movimientos_stock)
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
                "circuito": circuito,
                "motivo": motivo,
                "movimientos_stock": [
                    {"item_codigo": codigo, "cantidad": cantidad}
                    for codigo, cantidad in movimientos_stock
                ],
            },
        )
        return entrega
