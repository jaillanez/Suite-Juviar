"""Despacho durable de avisos de reposición a Compras."""

from __future__ import annotations

from ..domain.puertos_mvp import RepositorioStock, TransporteCorreo


class DespacharAvisosCompras:
    def __init__(
        self,
        stock: RepositorioStock,
        transporte: TransporteCorreo,
        destinatario: str,
    ) -> None:
        self._stock = stock
        self._transporte = transporte
        self._destinatario = destinatario

    def ejecutar(self, limite: int = 20) -> dict[str, int]:
        enviados = fallidos = 0
        for aviso in self._stock.reclamar_alertas(limite):
            aviso_id = int(aviso["id"])
            identificador = f"rrhh-epp-stock-{aviso_id}"
            try:
                self._transporte.enviar(
                    self._destinatario,
                    f"Reposición de EPP requerida: {aviso['item_codigo']}",
                    (
                        "Se alcanzó el mínimo de stock de EPP.\n\n"
                        f"Ítem: {aviso['item_codigo']}\n"
                        f"Disponible: {aviso['disponible']}\n"
                        f"Mínimo: {aviso['minimo']}\n"
                        f"Referencia: {identificador}\n"
                    ),
                    identificador,
                )
            except Exception as exc:  # noqa: BLE001 - frontera del worker; el aviso no se pierde
                self._stock.reintentar_alerta(aviso_id, str(exc))
                fallidos += 1
            else:
                self._stock.confirmar_alerta(aviso_id)
                enviados += 1
        return {"enviados": enviados, "fallidos": fallidos}
