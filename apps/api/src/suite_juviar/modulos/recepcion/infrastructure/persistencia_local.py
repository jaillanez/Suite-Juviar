"""Persistencia durable de Recepción para el entorno local de prueba."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from suite_juviar.modulos.recepcion.application.casos_uso import DatosIngreso
from suite_juviar.modulos.recepcion.domain.entidades import Pesada, Romaneo


class AbrirRomaneoSQLite:
    """Registra estado, outbox y auditoría en una única transacción SQLite."""

    def __init__(self, ruta: str | Path) -> None:
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self._conexion() as cn:
            cn.executescript(
                """
                CREATE TABLE IF NOT EXISTS romaneo (
                    id TEXT PRIMARY KEY, numero INTEGER NOT NULL UNIQUE,
                    productor_cuit TEXT NOT NULL, transportista_cuit TEXT NOT NULL,
                    chofer_dni TEXT NOT NULL, patente_chasis TEXT NOT NULL,
                    patente_acoplado TEXT, variedad TEXT NOT NULL, finca TEXT,
                    bruto_kg TEXT NOT NULL, origen_peso TEXT NOT NULL,
                    operador_legajo TEXT NOT NULL, estado TEXT NOT NULL,
                    abierto_en TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    id TEXT PRIMARY KEY, nombre TEXT NOT NULL, payload TEXT NOT NULL,
                    creado_en TEXT NOT NULL, enviado_en TEXT
                );
                CREATE TABLE IF NOT EXISTS auditoria (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, accion TEXT NOT NULL,
                    actor TEXT NOT NULL, entidad_id TEXT NOT NULL,
                    datos TEXT NOT NULL, momento TEXT NOT NULL
                );
                """
            )

    def _conexion(self) -> sqlite3.Connection:
        cn = sqlite3.connect(self.ruta)
        cn.execute("PRAGMA journal_mode=WAL")
        return cn

    async def __call__(self, datos: DatosIngreso) -> Romaneo:
        ahora = datetime.now(UTC)
        with self._conexion() as cn:
            cn.execute("BEGIN IMMEDIATE")
            numero = int(cn.execute("SELECT COALESCE(MAX(numero), 0) + 1 FROM romaneo").fetchone()[0])
            romaneo = Romaneo(
                numero=numero,
                productor_cuit=datos.productor_cuit,
                transportista_cuit=datos.transportista_cuit,
                chofer_dni=datos.chofer_dni,
                patente_chasis=datos.patente_chasis,
                patente_acoplado=datos.patente_acoplado,
                variedad=datos.variedad,
                finca=datos.finca,
                bruto=Pesada(
                    kg=datos.bruto_kg,
                    origen=datos.origen_peso,
                    registrada_en=ahora,
                    operador_legajo=datos.operador_legajo,
                ),
            )
            cn.execute(
                """INSERT INTO romaneo VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(romaneo.id), romaneo.numero, romaneo.productor_cuit,
                    romaneo.transportista_cuit, romaneo.chofer_dni, romaneo.patente_chasis,
                    romaneo.patente_acoplado, romaneo.variedad, romaneo.finca,
                    str(datos.bruto_kg), datos.origen_peso.value, datos.operador_legajo,
                    romaneo.estado.value, romaneo.abierto_en.isoformat(),
                ),
            )
            payload = {
                "romaneo_id": str(romaneo.id), "numero": romaneo.numero,
                "productor_cuit": romaneo.productor_cuit, "variedad": romaneo.variedad,
            }
            cn.execute(
                "INSERT INTO outbox(id,nombre,payload,creado_en) VALUES (?,?,?,?)",
                (str(uuid4()), "recepcion.romaneo_abierto", json.dumps(payload), ahora.isoformat()),
            )
            cn.execute(
                """INSERT INTO auditoria(accion,actor,entidad_id,datos,momento)
                   VALUES (?,?,?,?,?)""",
                (
                    "recepcion.romaneo.abierto", datos.operador_legajo, str(romaneo.id),
                    json.dumps({"bruto_kg": str(datos.bruto_kg), "origen": datos.origen_peso.value}),
                    ahora.isoformat(),
                ),
            )
        return romaneo
