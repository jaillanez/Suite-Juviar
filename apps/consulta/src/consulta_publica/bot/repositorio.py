"""Persistencia de la cola con privilegios separados para webhook y worker."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .archivos import Archivo
from .dialogo import MINUTOS_SESION, Cuenta, Estado, IdentificacionBloqueada
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
                """SELECT paso,clientecuit,pedido,turno,candidatas,actualizado
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
                tuple(fila["candidatas"] or ()),
            ),
            False,
        )

    def guardar_estado(self, telefono: str, estado: Estado) -> None:
        with self._conexion() as conexion:
            conexion.execute(
                """INSERT INTO consulta.bot_sesion(telefono,paso,clientecuit,pedido,turno,candidatas)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(telefono) DO UPDATE SET paso=EXCLUDED.paso,
                     clientecuit=EXCLUDED.clientecuit,pedido=EXCLUDED.pedido,
                     turno=EXCLUDED.turno,candidatas=EXCLUDED.candidatas,actualizado=now()""",
                (
                    telefono,
                    estado.paso,
                    estado.cuenta,
                    estado.pedido,
                    Jsonb(estado.turno.a_dict()) if estado.turno else None,
                    list(estado.candidatas) or None,
                ),
            )

    # --- Acceso sin alta: vínculo por cuenta, CUIT o patente (infra/044) ----------------

    def vinculo(self, telefono: str) -> Cuenta | None:
        """La cuenta a la que quedó vinculado un número que no está dado de alta."""
        with self._conexion() as conexion:
            fila = conexion.execute(
                """SELECT v.clientecuit, v.codigo, p.razonsocial, p.codigos
                   FROM consulta.bot_vinculo v JOIN fila.productor p USING (clientecuit)
                   WHERE v.telefono = %s""",
                (telefono,),
            ).fetchone()
        if not fila:
            return None
        codigo = fila["codigo"] or (fila["codigos"] or [fila["clientecuit"]])[0]
        return Cuenta(fila["clientecuit"], codigo, fila["razonsocial"])

    def identificador(self, telefono: str) -> IdentificadorBot:
        return IdentificadorBot(self._dsn, telefono)

    def cuentas_por_cuit(self, clientecuits: list[str] | tuple[str, ...]) -> list[Cuenta]:
        """Las cuentas entre las que elige quien escribió un CUIT o una patente con varias."""
        if not clientecuits:
            return []
        with self._conexion() as conexion:
            filas = conexion.execute(
                """SELECT clientecuit, razonsocial, codigos FROM fila.productor
                   WHERE clientecuit = ANY(%s)""",
                (list(clientecuits),),
            ).fetchall()
        por_cuit = {
            f["clientecuit"]: Cuenta(f["clientecuit"], (f["codigos"] or [f["clientecuit"]])[0], f["razonsocial"])
            for f in filas
        }
        # El orden es el de la pregunta: «2» tiene que ser la misma cuenta que se mostró segunda.
        return [por_cuit[c] for c in clientecuits if c in por_cuit]

    def vincular(self, telefono: str, cuenta: Cuenta) -> None:
        """La base sólo vincula una cuenta que este teléfono identificó en la última hora."""
        self._funcion("SELECT consulta.bot_vincular(%s, %s, %s) AS ok",
                      (telefono, cuenta.clientecuit, cuenta.codigo))

    def desvincular(self, telefono: str) -> None:
        with self._conexion() as conexion:
            conexion.execute("DELETE FROM consulta.bot_vinculo WHERE telefono = %s", (telefono,))

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

    def _marcar(self, funcion: str, id_: int, wamid: str | None, error: str | None, nota: str | None) -> None:
        """La nota (salió como texto porque Meta rechazó la plantilla) necesita infra/043; sin la
        migración se marca igual, sin la nota, para que el aviso no se reenvíe."""
        if funcion not in {"marcar_aviso", "marcar_aviso_personal"}:
            raise ValueError(funcion)
        if nota:
            try:
                with self._conexion() as conexion:
                    conexion.execute(f"SELECT fila.{funcion}(%s,%s,%s,%s)", (id_, wamid, error, nota))
                return
            except psycopg.errors.UndefinedFunction:
                pass
        with self._conexion() as conexion:
            conexion.execute(f"SELECT fila.{funcion}(%s,%s,%s)", (id_, wamid, error))

    def tomar_avisos_personal(self, lote: int = 20) -> list[dict]:
        with self._conexion() as conexion:
            return conexion.execute("SELECT * FROM fila.tomar_avisos_personal(%s)", (lote,)).fetchall()

    def marcar_aviso_personal(self, id_: int, wamid: str | None, error: str | None, nota: str | None = None) -> None:
        self._marcar("marcar_aviso_personal", id_, wamid, error, nota)

    def tomar_avisos(self, lote: int = 10) -> list[dict]:
        with self._conexion() as conexion:
            return conexion.execute("SELECT * FROM fila.tomar_avisos(%s)", (lote,)).fetchall()

    def marcar_aviso(self, id_: int, wamid: str | None, error: str | None, nota: str | None = None) -> None:
        self._marcar("marcar_aviso", id_, wamid, error, nota)

    def registrar_consulta(
        self, clientecuit: str, recurso: str, filas: int, telefono: str | None = None
    ) -> None:
        """Con teléfono: la consulta la hizo un número vinculado sin alta (infra/044)."""
        with self._conexion() as conexion:
            if telefono is None:
                conexion.execute(
                    """INSERT INTO consulta.bitacora_consulta
                           (cliente, clientecuit, recurso, filas)
                       VALUES ('bot-whatsapp', %s, %s, %s)""",
                    (clientecuit, recurso, filas),
                )
                return
            conexion.execute(
                """INSERT INTO consulta.bitacora_consulta
                       (cliente, clientecuit, recurso, filas, telefono)
                   VALUES ('bot-whatsapp-vinculo', %s, %s, %s, %s)""",
                (clientecuit, recurso, filas, telefono),
            )


class IdentificadorBot:
    """Busca la cuenta por código, CUIT o patente con ``consulta.bot_identificar``: la base anota
    cada intento y corta después de BOT_MAX_IDENTIFICACIONES_HORA intentos sin resultado."""

    def __init__(self, dsn: str, telefono: str, maximo: int | None = None) -> None:
        self._dsn = dsn
        self._telefono = telefono
        self._maximo = maximo if maximo is not None else max_identificaciones_hora()

    def buscar(self, por: str, dato: str) -> list[Cuenta]:
        try:
            with psycopg.connect(self._dsn, row_factory=dict_row, autocommit=True) as conexion:
                filas = conexion.execute(
                    """SELECT clientecuit, codigo, titular
                       FROM consulta.bot_identificar(%s, %s, %s, %s)""",
                    (self._telefono, por, dato, self._maximo),
                ).fetchall()
        except psycopg.errors.RaiseException as exc:
            if (exc.diag.message_primary or "") == "demasiados_intentos":
                raise IdentificacionBloqueada() from exc
            return []  # dato_invalido: el diálogo lo vuelve a pedir
        return [Cuenta(f["clientecuit"], f["codigo"], f["titular"]) for f in filas]


def max_identificaciones_hora() -> int:
    valor = int(os.environ.get("BOT_MAX_IDENTIFICACIONES_HORA", "10"))
    if not 1 <= valor <= 50:
        raise RuntimeError("BOT_MAX_IDENTIFICACIONES_HORA tiene que estar entre 1 y 50")
    return valor


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
