"""Persistencia de la cola con privilegios separados para webhook y worker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .archivos import Archivo
from .dialogo import MINUTOS_SESION, Cuenta, Estado
from .meta import MensajeEntrante
from .turnos import KG_POR_DEFECTO, Borrador, TurnoRechazado, TurnoVigente


class RepositorioWebhook:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def encolar(self, mensaje: MensajeEntrante) -> bool:
        with psycopg.connect(self._dsn) as conexion:
            fila = conexion.execute(
                """
                SELECT consulta.encolar_bot(%s, %s, %s, %s, %s) AS insertado
                """,
                (
                    mensaje.wamid,
                    mensaje.telefono,
                    mensaje.tipo,
                    mensaje.texto,
                    mensaje.enviado_en,
                ),
            ).fetchone()
        return bool(fila[0])


@dataclass(frozen=True)
class Pendiente:
    id: int
    telefono: str
    texto: str | None
    intentos: int


class RepositorioBot:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _conexion(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, row_factory=dict_row, autocommit=True)

    def tomar(self, lote: int = 20) -> list[Pendiente]:
        with self._conexion() as conexion:
            filas = conexion.execute(
                """
                UPDATE consulta.bot_entrada SET estado = 'tomado', tomado_en = now()
                WHERE id IN (
                    SELECT id FROM consulta.bot_entrada
                    WHERE estado = 'pendiente'
                       OR (estado = 'tomado' AND tomado_en < now() - interval '2 minutes')
                    ORDER BY recibido_en
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                )
                RETURNING id, telefono, texto, intentos
                """,
                (lote,),
            ).fetchall()
        return [Pendiente(**fila) for fila in filas]

    def productores(self, telefono: str) -> list[str]:
        with self._conexion() as conexion:
            filas = conexion.execute(
                """SELECT clientecuit FROM consulta.telefono_productor
                   WHERE telefono = %s AND activo
                     AND 'ver_informes' = ANY(tareas)
                   ORDER BY clientecuit""",
                (telefono,),
            ).fetchall()
        return [fila["clientecuit"] for fila in filas]

    def cuentas(self, telefono: str) -> list[Cuenta]:
        with self._conexion() as conexion:
            filas = conexion.execute(
                """SELECT p.clientecuit,p.razonsocial,p.codigos,t.tareas
                   FROM consulta.telefono_productor t
                   JOIN fila.productor p USING(clientecuit)
                   WHERE t.telefono=%s AND t.activo
                   ORDER BY p.razonsocial""",
                (telefono,),
            ).fetchall()
        return [
            Cuenta(
                f["clientecuit"],
                (f["codigos"] or [f["clientecuit"]])[0],
                f["razonsocial"],
                frozenset(f["tareas"] or ()),
            )
            for f in filas
        ]

    def permisos(self, telefono: str) -> set[str]:
        with self._conexion() as conexion:
            filas = conexion.execute(
                """SELECT unnest(tareas) tarea FROM consulta.telefono_productor
                   WHERE telefono=%s AND activo""",
                (telefono,),
            ).fetchall()
        return {f["tarea"] for f in filas}

    def estado(self, telefono: str, ahora: datetime | None = None) -> Estado:
        return self.estado_y_caducidad(telefono, ahora)[0]

    def estado_y_caducidad(
        self, telefono: str, ahora: datetime | None = None
    ) -> tuple[Estado, bool]:
        ahora = ahora or datetime.now(UTC)
        with self._conexion() as conexion:
            fila = conexion.execute(
                """SELECT paso,clientecuit,pedido,turno,actualizado
                   FROM consulta.bot_sesion WHERE telefono=%s""",
                (telefono,),
            ).fetchone()
        if not fila:
            return Estado(), False
        if fila["actualizado"] < ahora - timedelta(minutes=MINUTOS_SESION):
            return Estado(), True
        return (
            Estado(
                fila["paso"],
                fila["clientecuit"],
                fila["pedido"],
                Borrador.desde_dict(fila["turno"]),
            ),
            False,
        )

    def guardar_estado(self, telefono: str, estado: Estado) -> None:
        with self._conexion() as conexion:
            conexion.execute(
                """INSERT INTO consulta.bot_sesion(telefono,paso,clientecuit,pedido,turno)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT(telefono) DO UPDATE SET paso=EXCLUDED.paso,
                     clientecuit=EXCLUDED.clientecuit,pedido=EXCLUDED.pedido,
                     turno=EXCLUDED.turno,actualizado=now()""",
                (
                    telefono,
                    estado.paso,
                    estado.cuenta,
                    estado.pedido,
                    Jsonb(estado.turno.a_dict()) if estado.turno else None,
                ),
            )

    def turnos(self, telefono: str) -> TurnosBot:
        return TurnosBot(self._dsn, telefono)

    def guardar_archivo(self, archivo: Archivo, telefono: str) -> None:
        with self._conexion() as conexion:
            conexion.execute(
                """INSERT INTO consulta.bot_archivo
                   (token,extension,nombre,contenido,telefono,vence)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (
                    archivo.token,
                    archivo.extension,
                    archivo.nombre,
                    archivo.contenido,
                    telefono,
                    archivo.vence,
                ),
            )

    def limpiar_archivos(self) -> int:
        with self._conexion() as conexion:
            resultado = conexion.execute(
                "DELETE FROM consulta.bot_archivo WHERE vence<now()"
            )
        return resultado.rowcount

    def respuestas_ultima_hora(self, telefono: str) -> int:
        with self._conexion() as conexion:
            fila = conexion.execute(
                """SELECT count(*) AS n FROM consulta.bot_entrada
                   WHERE telefono = %s AND estado = 'respondido'
                     AND procesado_en > now() - interval '1 hour'""",
                (telefono,),
            ).fetchone()
        return fila["n"]

    def cerrar(
        self,
        id_: int,
        estado: str,
        respuesta: str | None = None,
        wamid_salida: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._conexion() as conexion:
            conexion.execute(
                """UPDATE consulta.bot_entrada SET estado = %s, respuesta = %s,
                       wamid_salida = %s, error = %s, procesado_en = now()
                   WHERE id = %s""",
                (estado, respuesta, wamid_salida, error, id_),
            )

    def reintentar(self, id_: int, error: str, maximo: int) -> None:
        with self._conexion() as conexion:
            conexion.execute(
                """UPDATE consulta.bot_entrada SET intentos = intentos + 1,
                       error = %s, tomado_en = NULL,
                       estado = CASE WHEN intentos + 1 >= %s
                                    THEN 'error' ELSE 'pendiente' END,
                       procesado_en = CASE WHEN intentos + 1 >= %s
                                          THEN now() ELSE NULL END
                   WHERE id = %s""",
                (error[:1000], maximo, maximo, id_),
            )

    def registrar_consulta(self, clientecuit: str, recurso: str, filas: int) -> None:
        with self._conexion() as conexion:
            conexion.execute(
                """INSERT INTO consulta.bitacora_consulta
                       (cliente, clientecuit, recurso, filas)
                   VALUES ('bot-whatsapp', %s, %s, %s)""",
                (clientecuit, recurso, filas),
            )


class TurnosBot:
    """Lecturas de cupo y reserva de turnos para un teléfono.

    La reserva pasa por ``fila.reservar_turno_whatsapp``: la base fija el canal y
    deja el teléfono como actor, y aplica las mismas reglas que Gestión.
    """

    def __init__(self, dsn: str, telefono: str) -> None:
        self._dsn = dsn
        self._telefono = telefono

    def _conexion(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, row_factory=dict_row, autocommit=True)

    def libres(self, sede: str, desde: date, hasta: date) -> dict[date, int]:
        with self._conexion() as conexion:
            filas = conexion.execute(
                """SELECT d.dia,
                          COALESCE(c.kg_dia, g.kg_dia) AS capacidad,
                          (SELECT COALESCE(sum(t.camiones::bigint * t.kg_por_camion), 0)
                             FROM fila.turno t
                            WHERE t.sede = %(sede)s AND t.fecha = d.dia
                              AND t.estado = 'activo') AS reservado
                   FROM generate_series(%(desde)s::date, %(hasta)s::date,
                                        interval '1 day') AS s(momento)
                   CROSS JOIN LATERAL (SELECT s.momento::date AS dia) d
                   LEFT JOIN fila.capacidad c ON c.sede = %(sede)s AND c.fecha = d.dia
                   LEFT JOIN fila.capacidad g ON g.sede = %(sede)s AND g.fecha IS NULL
                   ORDER BY d.dia""",
                {"sede": sede, "desde": desde, "hasta": hasta},
            ).fetchall()
        return {
            f["dia"]: max(int(f["capacidad"]) - int(f["reservado"]), 0)
            for f in filas
            if f["capacidad"] is not None
        }

    def tiene_organico(self, clientecuit: str, fecha: date) -> bool:
        with self._conexion() as conexion:
            fila = conexion.execute(
                """SELECT 1 FROM fila.productor_organico
                   WHERE clientecuit=%s AND (vence IS NULL OR vence >= %s)""",
                (clientecuit, fecha),
            ).fetchone()
        return fila is not None

    def kg_estimado(self, clientecuit: str) -> int:
        """Promedio de los últimos netos, redondeado a la centena (como la fila)."""
        with self._conexion() as conexion:
            fila = conexion.execute(
                """SELECT round(avg(neto), -2)::integer AS kg FROM (
                       SELECT neto FROM consulta.descarga_publica
                       WHERE clientecuit=%s AND estado='descargado' AND neto > 0
                       ORDER BY fecha DESC NULLS LAST LIMIT 30) ultimas""",
                (clientecuit,),
            ).fetchone()
        return fila["kg"] or KG_POR_DEFECTO

    def proximos(self, clientecuits: list[str], desde: date) -> list[TurnoVigente]:
        if not clientecuits:
            return []
        with self._conexion() as conexion:
            filas = conexion.execute(
                """SELECT id,sede,fecha,clientecuit,clientecodigo,camiones,camiones_usados,
                          kg_por_camion,declara_organica
                   FROM fila.turno
                   WHERE clientecuit = ANY(%s) AND fecha >= %s AND estado='activo'
                   ORDER BY fecha,sede,id LIMIT 20""",
                (clientecuits, desde),
            ).fetchall()
        return [_turno(f) for f in filas]

    def reservar(
        self,
        clientecuit: str,
        codigo: str,
        sede: str,
        fecha: date,
        camiones: int,
        kg_por_camion: int,
        organica: bool,
    ) -> TurnoVigente:
        try:
            with self._conexion() as conexion:
                fila = conexion.execute(
                    """SELECT id,sede,fecha,clientecuit,clientecodigo,camiones,camiones_usados,
                              kg_por_camion,declara_organica
                       FROM fila.reservar_turno_whatsapp(%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (sede, fecha, clientecuit, codigo, camiones, kg_por_camion, organica,
                     self._telefono),
                ).fetchone()
        except psycopg.errors.RaiseException as exc:
            # Sólo las reglas (P0001) se le muestran al productor; el resto se reintenta.
            raise TurnoRechazado(exc.diag.message_primary or "") from exc
        return _turno(fila)


def _turno(f: dict) -> TurnoVigente:
    return TurnoVigente(
        id=f["id"],
        sede=f["sede"],
        fecha=f["fecha"],
        clientecuit=f["clientecuit"],
        codigo=f["clientecodigo"],
        camiones=f["camiones"],
        camiones_usados=f["camiones_usados"],
        kg_por_camion=f["kg_por_camion"],
        organica=f["declara_organica"],
    )


class RepositorioArchivos:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def leer(self, token: str) -> dict | None:
        with psycopg.connect(self._dsn, row_factory=dict_row) as conexion:
            return conexion.execute(
                "SELECT * FROM consulta.leer_archivo(%s)", (token,)
            ).fetchone()
