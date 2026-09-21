"""Normalización Oracle y huella estable de V_DETALLE_MOVIMIENTOS."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256

MAPEO: dict[str, str] = {
    "ID": "id_origen",
    "NRO_DELEGACION": "nro_delegacion",
    "CIU": "ciu",
    "FECHA": "fecha",
    "NROINSCRIPTO": "nroinscripto",
    "RAZONSOCIAL": "razonsocial",
    "CUIT": "cuit",
    "CLIENTECODIGO": "clientecodigo",
    "CLIENTERAZONSOCIAL": "clienterazonsocial",
    "CLIENTECUIT": "clientecuit",
    "BRUTO": "bruto",
    "TARA": "tara",
    "NETO": "neto",
    "CODIGOTRANSPORTE": "codigotransporte",
    "MODELO": "modelo",
    "CHOFERCODE": "chofercode",
    "CHOFERDESCRIPCION": "choferdescripcion",
    "CODIGOVARIEDAD": "codigovariedad",
    "DESCVARIEDAD": "descvariedad",
    "AZUCAR": "azucar",
    "TIPOCOMERCIALIZACION": "tipocomercializacion",
    "OBSERVACION": "observacion",
    "COSECHA": "cosecha",
    "TIPOCOSECHA": "tipocosecha",
    "TIPOUVA": "tipouva",
}
COLUMNAS_ORIGEN = tuple(MAPEO)
COLUMNAS_DESTINO = tuple(MAPEO.values())

EN_DESCARGA = "en_descarga"
DESCARGADO = "descargado"
AUSENTE = "ausente_en_origen"


class FilaInvalida(ValueError):
    pass


@dataclass(frozen=True)
class FilaOrigen:
    sede: str
    ciu: str
    valores: dict[str, object]

    @classmethod
    def desde_oracle(cls, sede: str, crudo: dict[str, object]) -> FilaOrigen:
        valores: dict[str, object] = {}
        for origen, destino in MAPEO.items():
            valor = crudo.get(origen)
            if isinstance(valor, str):
                valor = valor.strip() or None
            valores[destino] = valor
        ciu = valores["ciu"]
        if ciu is None:
            raise FilaInvalida(f"fila sin CIU en {sede}: ID={valores['id_origen']}")
        valores["ciu"] = str(ciu).strip()
        if valores["id_origen"] is not None:
            valores["id_origen"] = str(valores["id_origen"])
        return cls(sede=sede, ciu=valores["ciu"], valores=valores)

    @property
    def estado(self) -> str:
        return EN_DESCARGA if self.valores["fecha"] is None else DESCARGADO

    @property
    def huella(self) -> str:
        return huella(self.valores)


def _canon(valor: object) -> object:
    if valor is None:
        return None
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float, Decimal)):
        return format(Decimal(str(valor)).normalize(), "f")
    return str(valor)


def huella(valores: dict[str, object]) -> str:
    canon = json.dumps(
        {clave: _canon(valores[clave]) for clave in sorted(valores)},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return sha256(canon.encode("utf-8")).hexdigest()
