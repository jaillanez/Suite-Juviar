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
from .turnos import Borrador, OfertaRechazada, OfertaVigente, TurnoVigente


class RepositorioWebhook:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def encolar(self, mensaje: MensajeEntrante) -> bool:
        with psycopg.connect(self._dsn) as conexion:
            if mensaje.media_id:
                # Foto o documento con su nombre y tipo (infra/042).
                fila = conexion.execute(
                    "SELECT consulta.encolar_bot_archivo(%s, %s, %s, %s, %s, %s, %s, %s) AS insertado",
                    (mensaje.wamid, mensaje.telefono, mensaje.tipo, mensaje.texto, mensaje.enviado_en,
                     mensaje.media_id, mensaje.media_nombre, mensaje.media_tipo),
                ).fetchone()
                return bool(fila[0])
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
class Personal:
    """Empleado de Juviar-ENAV registrado con su celular (infra/034)."""

    nombre: str
    empresa: str
    tipo: str


@dataclass(frozen=True)
class Pendiente:
    id: int
    telefono: str
    texto: str | None
    intentos: int
    tipo: str = "text"
    media_id: str | None = None
    media_nombre: str | None = None
    media_tipo: str | None = None


class RepositorioBot:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _conexion(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, row_factory=dict_row, autocommit=True, connect_timeout=10)

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
                RETURNING id, telefono, texto, intentos, tipo, media_id, media_nombre, media_tipo
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

    def personal(self, telefono: str) -> Personal | None:
        with self._conexion() as conexion:
            fila = conexion.execute(
                """SELECT nombre, empresa, tipo FROM consulta.telefono_personal
                   WHERE telefono = %s AND activo""",
                (telefono,),
            ).fetchone()
        return Personal(**fila) if fila else None

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

    # --- Avisos de la bodega al productor (asignación de días, postergación) ------------

    def registrar_mantenimiento(self, telefono: str, texto: str, foto: bytes | None, tipo_foto: str | None) -> int:
        """Foto y texto del personal para Mantenimiento (infra/041); la base controla quién puede."""
        with self._conexion() as conexion:
            try:
                fila = conexion.execute(
                    "SELECT fila.recibir_mensaje_mantenimiento(%s, %s, %s, %s) AS id",
                    (telefono, texto, foto, tipo_foto),
                ).fetchone()
            except psycopg.errors.RaiseException as exc:
                raise ValueError(exc.diag.message_primary or "no se pudo registrar") from exc
        return int(fila["id"])

    # --- RRHH por WhatsApp (infra/042) -------------------------------------------------

    def _funcion(self, consulta: str, parametros: tuple):
        """Llama una función de la base; sus reglas (P0001) vuelven como ValueError."""
        with self._conexion() as conexion:
            try:
                return conexion.execute(consulta, parametros).fetchone()
            except psycopg.errors.RaiseException as exc:
                raise ValueError(exc.diag.message_primary or "no se pudo registrar") from exc

    def registrar_rrhh(self, telefono: str, tipo: str, texto: str, archivo: bytes | None,
                       archivo_tipo: str | None, archivo_nombre: str | None) -> int:
        """Certificado médico o pedido de EPP del personal: queda para revisión de RRHH."""
        fila = self._funcion("SELECT fila.recibir_mensaje_rrhh(%s, %s, %s, %s, %s, %s) AS id",
                             (telefono, tipo, texto, archivo, archivo_tipo, archivo_nombre))
        return int(fila["id"])

    def registrar_cv(self, telefono: str, nombre: str, contenido: bytes, tipo: str) -> int:
        """CV de un número desconocido: Gestión lo incorpora a Selección."""
        fila = self._funcion("SELECT fila.recibir_cv_whatsapp(%s, %s, %s, %s) AS id",
                             (telefono, nombre, contenido, tipo))
        return int(fila["id"])

    def confirmacion_pendiente(self, telefono: str) -> str | None:
        """'esperando' o 'corrigiendo' si ese celular tiene un certificado esperando su respuesta."""
        fila = self._funcion("SELECT fila.confirmacion_certificado_pendiente(%s) AS estado", (telefono,))
        return fila["estado"] if fila else None

    def responder_certificado(self, telefono: str, respuesta: str, correccion: str | None = None) -> str | None:
        fila = self._funcion("SELECT fila.responder_certificado(%s, %s, %s) AS estado",
                             (telefono, respuesta, correccion))
        return fila["estado"] if fila else None

    def tomar_avisos_personal(self, lote: int = 20) -> list[dict]:
        with self._conexion() as conexion:
            return conexion.execute("SELECT * FROM fila.tomar_avisos_personal(%s)", (lote,)).fetchall()

    def marcar_aviso_personal(self, id_: int, wamid: str | None, error: str | None) -> None:
        with self._conexion() as conexion:
            conexion.execute("SELECT fila.marcar_aviso_personal(%s,%s,%s)", (id_, wamid, error))

    def tomar_avisos(self, lote: int = 10) -> list[dict]:
        with self._conexion() as conexion:
            return conexion.execute("SELECT * FROM fila.tomar_avisos(%s)", (lote,)).fetchall()

    def marcar_aviso(self, id_: int, wamid: str | None, error: str | None) -> None:
        with self._conexion() as conexion:
            conexion.execute("SELECT fila.marcar_aviso(%s,%s,%s)", (id_, wamid, error))

    def registrar_consulta(self, clientecuit: str, recurso: str, filas: int) -> None:
        with self._conexion() as conexion:
            conexion.execute(
                """INSERT INTO consulta.bitacora_consulta
                       (cliente, clientecuit, recurso, filas)
                   VALUES ('bot-whatsapp', %s, %s, %s)""",
                (clientecuit, recurso, filas),
            )


class TurnosBot:
    """Ofertas de uva y turnos de un teléfono.

    La oferta pasa por ``fila.ofrecer_uva_whatsapp``: la base fija el canal, deja el
    teléfono como actor y comprueba que ese teléfono pueda ofrecer para la cuenta.
    """

    def __init__(self, dsn: str, telefono: str) -> None:
        self._dsn = dsn
        self._telefono = telefono

    def _conexion(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, row_factory=dict_row, autocommit=True)

    def tiene_organico(self, clientecuit: str, fecha: date) -> bool:
        with self._conexion() as conexion:
            return conexion.execute(
                """SELECT 1 FROM fila.productor_organico
                   WHERE clientecuit=%s AND (vence IS NULL OR vence >= %s)""",
                (clientecuit, fecha),
            ).fetchone() is not None

    def variedades(self, clientecuit: str) -> list[str]:
        with self._conexion() as conexion:
            filas = conexion.execute(
                """SELECT initcap(btrim(variedad)) AS variedad FROM consulta.descarga_publica
                   WHERE clientecuit=%s AND estado='descargado' AND neto > 0
                     AND variedad IS NOT NULL AND btrim(variedad) <> ''
                     AND fecha > now() - interval '3 years'
                   GROUP BY 1 ORDER BY sum(neto) DESC LIMIT 12""",
                (clientecuit,),
            ).fetchall()
        return [f["variedad"] for f in filas]

    def ofrecer(
        self, pedido: str, clientecuit: str, codigo: str, sede: str, variedad: str, kg: int,
        organica: bool,
    ) -> OfertaVigente:
        try:
            with self._conexion() as conexion:
                fila = conexion.execute(
                    """SELECT id,sede,clientecuit,clientecodigo,variedad,kg,estado,detenida_hasta
                       FROM fila.ofrecer_uva_whatsapp(%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (pedido, sede, clientecuit, codigo, variedad, kg, organica, self._telefono),
                ).fetchone()
        except psycopg.errors.RaiseException as exc:
            # Sólo las reglas (P0001) se le muestran al productor; el resto se reintenta.
            raise OfertaRechazada(exc.diag.message_primary or "") from exc
        return _oferta(fila)

    def ofertas(self, clientecuits: list[str]) -> list[OfertaVigente]:
        if not clientecuits:
            return []
        with self._conexion() as conexion:
            filas = conexion.execute(
                """SELECT id,sede,clientecuit,clientecodigo,variedad,kg,estado,detenida_hasta
                   FROM fila.oferta
                   WHERE clientecuit = ANY(%s) AND estado <> 'desestimada'
                     AND temporada = (SELECT max(temporada) FROM fila.oferta
                                       WHERE clientecuit = ANY(%s))
                   ORDER BY creado_en, id LIMIT 20""",
                (clientecuits, clientecuits),
            ).fetchall()
        return [_oferta(f) for f in filas]

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


def _oferta(f: dict) -> OfertaVigente:
    return OfertaVigente(
        id=f["id"], sede=f["sede"], clientecuit=f["clientecuit"], codigo=f["clientecodigo"],
        variedad=f["variedad"], kg=f["kg"], estado=f["estado"], detenida_hasta=f["detenida_hasta"],
    )


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
