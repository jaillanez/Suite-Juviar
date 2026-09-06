"""Persistencia cifrada de CV y extracciones en PostgreSQL."""

from __future__ import annotations

import base64
import json
from dataclasses import asdict

import psycopg
from psycopg.rows import dict_row

from suite_juviar.plataforma.cripto.puertos import ProtectorDatosPersonales

from ..domain.modelos import CampoExtraido, CVOriginal, ExtraccionCV, OrigenCV


class EsquemaSeleccionFaltante(RuntimeError):
    pass


class SeleccionPostgreSQL:
    def __init__(self, dsn: str, protector: ProtectorDatosPersonales) -> None:
        self._dsn = dsn
        self._protector = protector
        try:
            with self._conectar() as cn, cn.cursor() as cur:
                cur.execute("SELECT to_regclass('seleccion.cv_original')")
                if cur.fetchone()[0] is None:
                    raise EsquemaSeleccionFaltante(
                        "Falta el esquema de Selección. Ejecute infra/006_seleccion_local.sql."
                    )
        except psycopg.Error as exc:
            raise EsquemaSeleccionFaltante(
                "No se pudo abrir PostgreSQL para Selección."
            ) from exc

    def _conectar(self, *, filas_dict: bool = False) -> psycopg.Connection:
        return psycopg.connect(self._dsn, row_factory=dict_row if filas_dict else None)

    def guardar_original(self, original: CVOriginal) -> bool:
        contenido_b64 = base64.b64encode(original.contenido).decode("ascii")
        with self._conectar() as cn, cn.cursor() as cur:
            cur.execute(
                """INSERT INTO seleccion.cv_original
                   (id, origen, referencia_hmac, referencia_cif, nombre_cif,
                    contenido_cif, sha256, recibido_en, incorporado_en,
                    dueno_dato, fuente_simulada)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING RETURNING id""",
                (
                    original.id,
                    original.origen.value,
                    self._protector.indice(original.referencia_fuente),
                    self._protector.cifrar(original.referencia_fuente),
                    self._protector.cifrar(original.nombre_archivo),
                    self._protector.cifrar(contenido_b64),
                    original.sha256,
                    original.recibido_en,
                    original.incorporado_en,
                    original.dueno_dato,
                    original.fuente_simulada,
                ),
            )
            return cur.fetchone() is not None

    def obtener_original(self, id_original: str) -> CVOriginal | None:
        with self._conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute("SELECT * FROM seleccion.cv_original WHERE id = %s", (id_original,))
            fila = cur.fetchone()
            if fila is None:
                return None
            return CVOriginal(
                id=str(fila["id"]),
                origen=OrigenCV(str(fila["origen"])),
                referencia_fuente=self._protector.descifrar(bytes(fila["referencia_cif"])),
                nombre_archivo=self._protector.descifrar(bytes(fila["nombre_cif"])),
                contenido=base64.b64decode(
                    self._protector.descifrar(bytes(fila["contenido_cif"])),
                    validate=True,
                ),
                sha256=str(fila["sha256"]),
                recibido_en=fila["recibido_en"],
                incorporado_en=fila["incorporado_en"],
                dueno_dato=str(fila["dueno_dato"]),
                fuente_simulada=bool(fila["fuente_simulada"]),
            )

    def existe_referencia(self, referencia_fuente: str) -> bool:
        indice = self._protector.indice(referencia_fuente)
        with self._conectar() as cn, cn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM seleccion.cv_original WHERE referencia_hmac = %s",
                (indice,),
            )
            return cur.fetchone() is not None

    def guardar_extraccion(self, extraccion: ExtraccionCV) -> None:
        datos = json.dumps(
            {
                "campos": [asdict(campo) for campo in extraccion.campos],
                "campos_pendientes": extraccion.campos_pendientes,
            },
            ensure_ascii=False,
        )
        with self._conectar() as cn, cn.cursor() as cur:
            cur.execute(
                """INSERT INTO seleccion.extraccion_cv
                   (id_original, datos_cif, extraido_en, estado)
                   VALUES (%s,%s,%s,%s)
                   ON CONFLICT (id_original) DO UPDATE
                   SET datos_cif = EXCLUDED.datos_cif,
                       extraido_en = EXCLUDED.extraido_en,
                       estado = EXCLUDED.estado""",
                (
                    extraccion.id_original,
                    self._protector.cifrar(datos),
                    extraccion.extraido_en,
                    extraccion.estado,
                ),
            )

    def obtener_extraccion(self, id_original: str) -> ExtraccionCV | None:
        with self._conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute(
                "SELECT * FROM seleccion.extraccion_cv WHERE id_original = %s",
                (id_original,),
            )
            fila = cur.fetchone()
            if fila is None:
                return None
            datos = json.loads(self._protector.descifrar(bytes(fila["datos_cif"])))
            return ExtraccionCV(
                id_original=str(fila["id_original"]),
                campos=tuple(CampoExtraido(**campo) for campo in datos["campos"]),
                campos_pendientes=tuple(datos["campos_pendientes"]),
                extraido_en=fila["extraido_en"],
                estado=str(fila["estado"]),
            )


def datos_visibles_en_tabla(dsn: str, id_original: str) -> dict[str, object] | None:
    """Sólo para prueba negativa: permite demostrar que no hay texto personal visible."""
    with psycopg.connect(dsn, row_factory=dict_row) as cn, cn.cursor() as cur:
        cur.execute(
            """SELECT id, origen, referencia_hmac, sha256, dueno_dato,
                      fuente_simulada, referencia_cif, nombre_cif, contenido_cif
               FROM seleccion.cv_original WHERE id = %s""",
            (id_original,),
        )
        return cur.fetchone()
