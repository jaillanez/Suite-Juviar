"""Repositorio PostgreSQL con identificadores personales cifrados."""

from __future__ import annotations

from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from suite_juviar.plataforma.cripto.puertos import ProtectorDatosPersonales

from ..domain.modelos import AnulacionAsistencia, Asistencia, Dictado, Participante, Tema


class EsquemaCapacitacionFaltante(RuntimeError):
    pass


class CapacitacionPostgreSQL:
    def __init__(self, dsn: str, protector: ProtectorDatosPersonales) -> None:
        self._dsn = dsn
        self._protector = protector
        try:
            with self._conectar() as cn, cn.cursor() as cur:
                cur.execute("SELECT to_regclass('capacitacion.tema')")
                if cur.fetchone()[0] is None:
                    raise EsquemaCapacitacionFaltante(
                        "Falta el esquema. Ejecute infra/007_capacitacion_local.sql."
                    )
        except psycopg.Error as exc:
            raise EsquemaCapacitacionFaltante(
                "No se pudo abrir PostgreSQL para Capacitación."
            ) from exc

    def _conectar(self, *, filas_dict: bool = False) -> psycopg.Connection:
        return psycopg.connect(self._dsn, row_factory=dict_row if filas_dict else None)

    def guardar_tema(self, tema: Tema) -> None:
        with self._conectar() as cn, cn.cursor() as cur:
            cur.execute(
                """INSERT INTO capacitacion.tema (id, nombre, horas, dueno_dato)
                   VALUES (%s,%s,%s,'RRHH') ON CONFLICT (id) DO NOTHING""",
                (tema.id, tema.nombre, tema.horas),
            )

    def guardar_dictado(self, dictado: Dictado) -> None:
        with self._conectar() as cn, cn.cursor() as cur:
            cur.execute(
                """INSERT INTO capacitacion.dictado (id, tema_id, fecha, instructor)
                   VALUES (%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                (dictado.id, dictado.tema_id, dictado.fecha, dictado.instructor),
            )

    def guardar_asistencia(self, asistencia: Asistencia) -> None:
        with self._conectar() as cn, cn.cursor() as cur:
            cur.execute(
                """INSERT INTO capacitacion.asistencia
                   (dictado_id, legajo_hmac, legajo_cif, nombre_cif, supervisor,
                    presente, firma_id, estado_firma)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (dictado_id, legajo_hmac) DO NOTHING""",
                (
                    asistencia.dictado_id,
                    self._protector.indice(asistencia.participante.legajo),
                    self._protector.cifrar(asistencia.participante.legajo),
                    self._protector.cifrar(asistencia.participante.nombre_completo),
                    asistencia.participante.supervisor,
                    asistencia.presente,
                    asistencia.firma_id,
                    asistencia.estado_firma,
                ),
            )

    def anular_asistencia(self, anulacion: AnulacionAsistencia) -> None:
        legajo_hmac = self._protector.indice(anulacion.legajo)
        with self._conectar() as cn, cn.cursor() as cur:
            cur.execute(
                """INSERT INTO capacitacion.asistencia_anulacion
                   (asistencia_id, motivo, anulada_por_hmac, anulada_por_cif, anulada_en)
                   SELECT id, %s, %s, %s, %s FROM capacitacion.asistencia
                   WHERE dictado_id = %s AND legajo_hmac = %s
                   ON CONFLICT (asistencia_id) DO NOTHING RETURNING asistencia_id""",
                (
                    anulacion.motivo,
                    self._protector.indice(anulacion.anulada_por),
                    self._protector.cifrar(anulacion.anulada_por),
                    anulacion.anulada_en,
                    anulacion.dictado_id,
                    legajo_hmac,
                ),
            )
            if cur.fetchone() is None and self.obtener_anulacion(
                anulacion.dictado_id,
                anulacion.legajo,
            ) is None:
                raise ValueError("No existe la asistencia")

    def obtener_anulacion(
        self,
        dictado_id: str,
        legajo: str,
    ) -> AnulacionAsistencia | None:
        with self._conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute(
                """SELECT a.dictado_id, a.legajo_cif, x.motivo,
                          x.anulada_por_cif, x.anulada_en
                   FROM capacitacion.asistencia a
                   JOIN capacitacion.asistencia_anulacion x ON x.asistencia_id = a.id
                   WHERE a.dictado_id = %s AND a.legajo_hmac = %s""",
                (dictado_id, self._protector.indice(legajo)),
            )
            fila = cur.fetchone()
            if fila is None:
                return None
            return AnulacionAsistencia(
                dictado_id=str(fila["dictado_id"]),
                legajo=self._protector.descifrar(bytes(fila["legajo_cif"])),
                motivo=str(fila["motivo"]),
                anulada_por=self._protector.descifrar(bytes(fila["anulada_por_cif"])),
                anulada_en=fila["anulada_en"],  # type: ignore[arg-type]
            )

    def obtener_tema(self, tema_id: str) -> Tema | None:
        with self._conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute("SELECT * FROM capacitacion.tema WHERE id = %s", (tema_id,))
            fila = cur.fetchone()
            return self._tema(fila) if fila else None

    def obtener_dictado(self, dictado_id: str) -> Dictado | None:
        with self._conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute("SELECT * FROM capacitacion.dictado WHERE id = %s", (dictado_id,))
            fila = cur.fetchone()
            return self._dictado(fila) if fila else None

    def dictados_del_tema(self, tema_id: str) -> list[Dictado]:
        with self._conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute(
                "SELECT * FROM capacitacion.dictado WHERE tema_id = %s ORDER BY fecha, id",
                (tema_id,),
            )
            return [self._dictado(fila) for fila in cur.fetchall()]

    def asistencias_del_dictado(self, dictado_id: str) -> list[Asistencia]:
        with self._conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute(
                """SELECT a.* FROM capacitacion.asistencia a
                   LEFT JOIN capacitacion.asistencia_anulacion x ON x.asistencia_id = a.id
                   WHERE a.dictado_id = %s AND x.asistencia_id IS NULL ORDER BY a.id""",
                (dictado_id,),
            )
            return [self._asistencia(fila) for fila in cur.fetchall()]

    def todas_las_asistencias(self) -> list[Asistencia]:
        with self._conectar(filas_dict=True) as cn, cn.cursor() as cur:
            cur.execute(
                """SELECT a.* FROM capacitacion.asistencia a
                   LEFT JOIN capacitacion.asistencia_anulacion x ON x.asistencia_id = a.id
                   WHERE x.asistencia_id IS NULL ORDER BY a.id"""
            )
            return [self._asistencia(fila) for fila in cur.fetchall()]

    @staticmethod
    def _tema(fila: dict[str, object]) -> Tema:
        return Tema(str(fila["id"]), str(fila["nombre"]), float(fila["horas"]))

    @staticmethod
    def _dictado(fila: dict[str, object]) -> Dictado:
        return Dictado(
            str(fila["id"]),
            str(fila["tema_id"]),
            fila["fecha"],  # type: ignore[arg-type]
            str(fila["instructor"]),
        )

    def _asistencia(self, fila: dict[str, object]) -> Asistencia:
        return Asistencia(
            dictado_id=str(fila["dictado_id"]),
            participante=Participante(
                legajo=self._protector.descifrar(bytes(fila["legajo_cif"])),
                nombre_completo=self._protector.descifrar(bytes(fila["nombre_cif"])),
                supervisor=bool(fila["supervisor"]),
            ),
            presente=bool(fila["presente"]),
            firma_id=UUID(str(fila["firma_id"])) if fila["firma_id"] else None,
            estado_firma=str(fila["estado_firma"]),
        )


def asistencia_visible(dsn: str, dictado_id: str) -> list[dict[str, object]]:
    """Lectura de prueba para demostrar que legajo y nombre no están en claro."""
    with psycopg.connect(dsn, row_factory=dict_row) as cn, cn.cursor() as cur:
        cur.execute(
            """SELECT dictado_id, legajo_hmac, legajo_cif, nombre_cif, supervisor,
                      presente, estado_firma
               FROM capacitacion.asistencia WHERE dictado_id = %s""",
            (dictado_id,),
        )
        return list(cur.fetchall())
