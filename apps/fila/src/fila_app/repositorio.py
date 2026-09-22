from __future__ import annotations

import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
from modulos.fila.cupo import Reserva
from modulos.fila.cupo import validar as validar_cupo
from modulos.fila.estados import MINUTOS_VENCE_PENDIENTE
from modulos.fila.estados import validar as validar_estado
from modulos.fila.orden import EnEspera, elegir_llamado, grupo, ordenar, posicion
from modulos.fila.patente import normalizar
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def _ahora() -> datetime:
    return datetime.now(UTC)


def _validar_momento(momento: datetime) -> datetime:
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    ahora = _ahora()
    if momento > ahora + timedelta(minutes=2) or momento < ahora - timedelta(hours=12):
        raise ValueError("la hora de la tablet está fuera del rango permitido")
    return momento


class RepositorioFila:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def conexion(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def expirar(self) -> int:
        with self.conexion() as cn:
            filas = cn.execute(
                """UPDATE fila.viaje SET estado='cancelado', cerrado_en=now(),
                          motivo_cierre='vencido_sin_confirmar'
                   WHERE estado='pendiente'
                     AND registrado_en < now() - (%s * interval '1 minute')
                   RETURNING id""",
                (MINUTOS_VENCE_PENDIENTE,),
            ).fetchall()
            if filas:
                cn.executemany(
                    """INSERT INTO fila.evento(viaje_id,tipo,actor,motivo)
                       VALUES (%s,'cancelado','sistema','vencido_sin_confirmar')""",
                    [(fila["id"],) for fila in filas],
                )
        return len(filas)

    def alta_publica(
        self,
        sede: str,
        patente: str,
        productor: str,
        telefono: str | None,
        id_cliente: UUID,
        ip: str,
    ) -> dict[str, Any]:
        patente = normalizar(patente)
        ticket = secrets.token_urlsafe(32)
        with self.conexion() as cn:
            usados = cn.execute(
                """SELECT count(*) n FROM fila.evento
                   WHERE tipo='registro_publico' AND detalle->>'ip'=%s
                     AND momento > now() - interval '1 hour'""",
                (ip,),
            ).fetchone()["n"]
            if usados >= 5:
                raise PermissionError("límite de cinco registros por hora")
            fila = cn.execute(
                """INSERT INTO fila.viaje
                       (id_cliente,ticket,productor_texto,sede,patente,chofer_tel,origen,estado)
                   VALUES (%s,%s,%s,%s,%s,%s,'qr','pendiente')
                   ON CONFLICT (id_cliente) DO UPDATE SET id_cliente=EXCLUDED.id_cliente
                   RETURNING id,ticket,estado,patente""",
                (id_cliente, ticket, productor.strip(), sede, patente, telefono),
            ).fetchone()
            cn.execute(
                """INSERT INTO fila.evento(id_cliente,viaje_id,tipo,actor,detalle)
                   VALUES (%s,%s,'registro_publico',%s,%s)
                   ON CONFLICT (id_cliente) DO NOTHING""",
                (
                    id_cliente,
                    fila["id"],
                    f"chofer:{telefono or 'sin-telefono'}",
                    Jsonb({"ip": ip}),
                ),
            )
        return dict(fila)

    def autocompletar(self, patente: str) -> dict[str, str] | None:
        patente = normalizar(patente)
        with self.conexion() as cn:
            fila = cn.execute(
                """SELECT ultimo_chofer_nombre, ultimo_chofer_tel, ultimo_clientecuit
                   FROM fila.vehiculo WHERE patente=%s""",
                (patente,),
            ).fetchone()
        if not fila:
            return None
        nombre = (fila["ultimo_chofer_nombre"] or "").strip()
        partes = nombre.split()
        enmascarado = f"{partes[0]} {partes[1][0]}." if len(partes) > 1 else nombre
        return {"chofer": enmascarado, "productor": "Productor conocido"}

    def ticket(self, ticket: str) -> dict[str, Any] | None:
        self.expirar()
        with self.conexion() as cn:
            viaje = cn.execute(
                """SELECT id,sede,patente,estado,numero_dia,confirmado_en
                   FROM fila.viaje WHERE ticket=%s""",
                (ticket,),
            ).fetchone()
            if not viaje:
                return None
            if viaje["estado"] == "en_espera":
                fila, certificados = self._fila(cn, viaje["sede"])
                viaje["posicion"] = posicion(fila, viaje["id"], certificados)
                viaje["adelante"] = max((viaje["posicion"] or 1) - 1, 0)
        return dict(viaje)

    def _fila(self, cn, sede: str) -> tuple[list[EnEspera], frozenset[str]]:
        filas = cn.execute(
            """SELECT v.id,v.clientecuit,v.declara_organica,v.confirmado_en,
                      (v.turno_id IS NOT NULL) con_turno
               FROM fila.viaje v WHERE v.sede=%s AND v.estado='en_espera'""",
            (sede,),
        ).fetchall()
        certificados = frozenset(
            fila["clientecuit"]
            for fila in cn.execute(
                """SELECT clientecuit FROM fila.productor_organico
                   WHERE vence IS NULL OR vence >= current_date"""
            ).fetchall()
        )
        return [EnEspera(**dict(fila)) for fila in filas], certificados

    def tablero(self, sede: str) -> dict[str, list[dict[str, Any]]]:
        self.expirar()
        with self.conexion() as cn:
            pendientes = cn.execute(
                """SELECT id,patente,productor_texto,registrado_en FROM fila.viaje
                   WHERE sede=%s AND estado='pendiente' ORDER BY registrado_en""",
                (sede,),
            ).fetchall()
            fila, certificados = self._fila(cn, sede)
            por_id = {
                f["id"]: dict(f)
                for f in cn.execute(
                    """SELECT id,numero_dia,patente,confirmado_en,clientecuit,
                              declara_organica,(turno_id IS NOT NULL) con_turno
                       FROM fila.viaje WHERE sede=%s AND estado='en_espera'""",
                    (sede,),
                ).fetchall()
            }
            espera = []
            for elemento in ordenar(fila, certificados):
                dato = por_id[elemento.id]
                dato["grupo"] = grupo(elemento, certificados)
                espera.append(dato)
            llamados = cn.execute(
                """SELECT id,numero_dia,patente,llamado_en FROM fila.viaje
                   WHERE sede=%s AND estado='llamado' ORDER BY llamado_en""",
                (sede,),
            ).fetchall()
        return {
            "pendientes": [dict(f) for f in pendientes],
            "espera": espera,
            "llamados": [dict(f) for f in llamados],
        }

    def confirmar(
        self,
        viaje_id: int,
        clientecuit: str,
        clientecodigo: str | None,
        declara_organica: bool,
        actor: str,
        id_cliente: UUID,
        momento_cliente: datetime,
    ) -> dict[str, Any]:
        momento_cliente = _validar_momento(momento_cliente)
        with self.conexion() as cn:
            if cn.execute("SELECT 1 FROM fila.evento WHERE id_cliente=%s", (id_cliente,)).fetchone():
                return dict(cn.execute("SELECT * FROM fila.viaje WHERE id=%s", (viaje_id,)).fetchone())
            viaje = cn.execute(
                "SELECT * FROM fila.viaje WHERE id=%s FOR UPDATE", (viaje_id,)
            ).fetchone()
            if not viaje or viaje["estado"] != "pendiente":
                raise ValueError("el camión ya no está pendiente")
            fecha = momento_cliente.date()
            turno = cn.execute(
                """SELECT id FROM fila.turno WHERE sede=%s AND fecha=%s
                     AND clientecuit=%s AND estado='activo' AND camiones_usados < camiones
                   ORDER BY creado_en FOR UPDATE LIMIT 1""",
                (viaje["sede"], fecha, clientecuit),
            ).fetchone()
            if turno:
                cn.execute(
                    "UPDATE fila.turno SET camiones_usados=camiones_usados+1 WHERE id=%s",
                    (turno["id"],),
                )
            numero = cn.execute(
                """SELECT COALESCE(max(numero_dia),0)+1 n FROM fila.viaje
                   WHERE sede=%s AND fecha_operativa=%s""",
                (viaje["sede"], fecha),
            ).fetchone()["n"]
            actualizado = cn.execute(
                """UPDATE fila.viaje SET estado='en_espera',clientecuit=%s,
                          clientecodigo=%s,declara_organica=%s,turno_id=%s,
                          confirmado_en=%s,confirmado_por=%s,fecha_operativa=%s,numero_dia=%s
                   WHERE id=%s RETURNING *""",
                (
                    clientecuit,
                    clientecodigo,
                    declara_organica,
                    turno["id"] if turno else None,
                    momento_cliente,
                    actor,
                    fecha,
                    numero,
                    viaje_id,
                ),
            ).fetchone()
            cn.execute(
                """INSERT INTO fila.evento
                       (id_cliente,viaje_id,tipo,actor,momento_cliente,detalle)
                   VALUES (%s,%s,'confirmado',%s,%s,%s)""",
                (id_cliente, viaje_id, actor, momento_cliente, Jsonb({"turno": bool(turno)})),
            )
        return dict(actualizado)

    def alta_directa(self, datos: dict[str, Any], actor: str) -> dict[str, Any]:
        momento = _validar_momento(datos["momento_cliente"])
        patente = normalizar(datos["patente"])
        with self.conexion() as cn:
            existente = cn.execute(
                """SELECT v.* FROM fila.viaje v JOIN fila.evento e ON e.viaje_id=v.id
                   WHERE e.id_cliente=%s""",
                (datos["id_cliente"],),
            ).fetchone()
            if existente:
                return dict(existente)
            turno = cn.execute(
                """SELECT id FROM fila.turno WHERE sede=%s AND fecha=%s
                     AND clientecuit=%s AND estado='activo' AND camiones_usados<camiones
                   ORDER BY creado_en FOR UPDATE LIMIT 1""",
                (datos["sede"], momento.date(), datos["clientecuit"]),
            ).fetchone()
            if turno:
                cn.execute(
                    "UPDATE fila.turno SET camiones_usados=camiones_usados+1 WHERE id=%s",
                    (turno["id"],),
                )
            numero = cn.execute(
                """SELECT COALESCE(max(numero_dia),0)+1 n FROM fila.viaje
                   WHERE sede=%s AND fecha_operativa=%s""",
                (datos["sede"], momento.date()),
            ).fetchone()["n"]
            viaje = cn.execute(
                """INSERT INTO fila.viaje
                   (id_cliente,ticket,productor_texto,sede,patente,chofer_tel,clientecuit,
                    clientecodigo,declara_organica,turno_id,origen,estado,fecha_operativa,
                    numero_dia,confirmado_en,confirmado_por)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'guardia','en_espera',
                           %s,%s,%s,%s) RETURNING *""",
                (
                    datos["id_cliente"],
                    secrets.token_urlsafe(32),
                    datos["productor"],
                    datos["sede"],
                    patente,
                    datos.get("telefono"),
                    datos["clientecuit"],
                    datos.get("clientecodigo"),
                    datos["declara_organica"],
                    turno["id"] if turno else None,
                    momento.date(),
                    numero,
                    momento,
                    actor,
                ),
            ).fetchone()
            cn.execute(
                """INSERT INTO fila.evento
                   (id_cliente,viaje_id,tipo,actor,momento_cliente,detalle)
                   VALUES (%s,%s,'alta_directa',%s,%s,%s)""",
                (
                    datos["id_cliente"],
                    viaje["id"],
                    actor,
                    momento,
                    Jsonb({"turno": bool(turno)}),
                ),
            )
        return dict(viaje)

    def accionar(
        self,
        viaje_id: int,
        accion: str,
        actor: str,
        id_cliente: UUID,
        momento_cliente: datetime,
        motivo: str | None = None,
    ) -> dict[str, Any]:
        momento_cliente = _validar_momento(momento_cliente)
        destinos = {"llamar": "llamado", "paso": "en_bascula", "no_vino": "en_espera"}
        destino = destinos[accion]
        with self.conexion() as cn:
            if cn.execute("SELECT 1 FROM fila.evento WHERE id_cliente=%s", (id_cliente,)).fetchone():
                return dict(cn.execute("SELECT * FROM fila.viaje WHERE id=%s", (viaje_id,)).fetchone())
            viaje = cn.execute(
                "SELECT * FROM fila.viaje WHERE id=%s FOR UPDATE", (viaje_id,)
            ).fetchone()
            if not viaje:
                raise ValueError("viaje inexistente")
            validar_estado(viaje["estado"], destino)
            detalle: dict[str, Any] = {}
            if accion == "llamar":
                fila, certificados = self._fila(cn, viaje["sede"])
                elegido, salteados = elegir_llamado(fila, certificados, viaje_id, motivo)
                detalle["salteados"] = salteados
                for salteado in salteados:
                    cn.execute(
                        """INSERT INTO fila.evento
                               (viaje_id,tipo,actor,motivo,detalle,momento_cliente)
                           VALUES (%s,'salteado',%s,%s,%s,%s)""",
                        (
                            salteado,
                            actor,
                            motivo,
                            Jsonb({"elegido": elegido.id}),
                            momento_cliente,
                        ),
                    )
            campos = {
                "llamar": "llamado_en=%s,llamado_por=%s",
                "paso": "en_bascula_en=%s",
                "no_vino": "llamado_en=NULL,llamado_por=NULL",
            }
            parametros: tuple[Any, ...]
            if accion == "llamar":
                parametros = (destino, momento_cliente, actor, viaje_id)
            elif accion == "paso":
                parametros = (destino, momento_cliente, viaje_id)
            else:
                parametros = (destino, viaje_id)
            actualizado = cn.execute(
                f"UPDATE fila.viaje SET estado=%s,{campos[accion]} WHERE id=%s RETURNING *",
                parametros,
            ).fetchone()
            cn.execute(
                """INSERT INTO fila.evento
                       (id_cliente,viaje_id,tipo,actor,motivo,detalle,momento_cliente)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (id_cliente, viaje_id, accion, actor, motivo, Jsonb(detalle), momento_cliente),
            )
        return dict(actualizado)

    def reservar_turno(self, datos: dict[str, Any]) -> dict[str, Any]:
        fecha = date.fromisoformat(datos["fecha"])
        reserva = Reserva(datos["camiones"], datos["kg_por_camion"])
        with self.conexion() as cn:
            capacidad = cn.execute(
                """SELECT * FROM fila.capacidad WHERE sede=%s AND fecha=%s FOR UPDATE""",
                (datos["sede"], fecha),
            ).fetchone()
            if not capacidad:
                capacidad = cn.execute(
                    """SELECT * FROM fila.capacidad WHERE sede=%s AND fecha IS NULL FOR UPDATE""",
                    (datos["sede"],),
                ).fetchone()
            if not capacidad:
                raise ValueError("la bodega todavía no definió capacidad para esa sede")
            reservado = cn.execute(
                """SELECT COALESCE(sum(camiones*kg_por_camion),0) kg FROM fila.turno
                   WHERE sede=%s AND fecha=%s AND estado='activo'""",
                (datos["sede"], fecha),
            ).fetchone()["kg"]
            validar_cupo(reserva, capacidad["kg_dia"], reservado)
            if datos["declara_organica"]:
                certificado = cn.execute(
                    """SELECT 1 FROM fila.productor_organico WHERE clientecuit=%s
                       AND (vence IS NULL OR vence >= %s)""",
                    (datos["clientecuit"], fecha),
                ).fetchone()
                if not certificado:
                    raise ValueError("el productor no tiene certificado orgánico vigente")
            turno = cn.execute(
                """INSERT INTO fila.turno
                       (sede,fecha,clientecuit,clientecodigo,camiones,kg_por_camion,
                        declara_organica,pedido_por,canal)
                   VALUES (%(sede)s,%(fecha)s,%(clientecuit)s,%(clientecodigo)s,
                           %(camiones)s,%(kg_por_camion)s,%(declara_organica)s,
                           %(pedido_por)s,%(canal)s) RETURNING *""",
                {**datos, "fecha": fecha},
            ).fetchone()
        return dict(turno)

    def cerrar_con_descargas(self) -> tuple[int, int]:
        """Vincula en orden; deja sin tocar grupos donde el orden no alcanza."""
        vinculados = 0
        ambiguos = 0
        with self.conexion() as cn:
            viajes = cn.execute(
                """SELECT * FROM fila.viaje WHERE estado='en_bascula'
                     AND descarga_id IS NULL ORDER BY clientecuit,sede,en_bascula_en,id
                   FOR UPDATE"""
            ).fetchall()
            usados = {
                fila["descarga_id"]
                for fila in cn.execute(
                    "SELECT descarga_id FROM fila.viaje WHERE descarga_id IS NOT NULL"
                ).fetchall()
            }
            for viaje in viajes:
                candidatos = cn.execute(
                    """SELECT id_suite,fecha FROM consulta.descarga_publica
                       WHERE clientecuit=%s AND sede=%s AND estado='descargado'
                         AND fecha >= %s AND fecha <= %s + interval '3 hours'
                         AND id_suite IS NOT NULL ORDER BY fecha,id_suite""",
                    (
                        viaje["clientecuit"],
                        viaje["sede"],
                        viaje["en_bascula_en"],
                        viaje["en_bascula_en"],
                    ),
                ).fetchall()
                candidatos = [c for c in candidatos if c["id_suite"] not in usados]
                if not candidatos:
                    continue
                misma_fecha = [c for c in candidatos if c["fecha"] == candidatos[0]["fecha"]]
                if len(misma_fecha) > 1:
                    ambiguos += 1
                    continue
                descarga = candidatos[0]
                cn.execute(
                    """UPDATE fila.viaje SET estado='descargado',descarga_id=%s,
                              cerrado_en=now() WHERE id=%s""",
                    (descarga["id_suite"], viaje["id"]),
                )
                cn.execute(
                    """INSERT INTO fila.evento(viaje_id,tipo,actor,detalle)
                       VALUES (%s,'descargado','sistema',%s)""",
                    (viaje["id"], Jsonb({"descarga_id": descarga["id_suite"]})),
                )
                usados.add(descarga["id_suite"])
                vinculados += 1
        return vinculados, ambiguos


class RepositorioPublico:
    """El rol público sólo ejecuta funciones acotadas; no lee tablas."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def conexion(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def alta_publica(
        self,
        sede: str,
        patente: str,
        productor: str,
        telefono: str | None,
        id_cliente: UUID,
        ip: str,
    ) -> dict[str, Any]:
        patente = normalizar(patente)
        with self.conexion() as cn:
            try:
                fila = cn.execute(
                    "SELECT * FROM fila.registrar_llegada(%s,%s,%s,%s,%s,%s,%s)",
                    (
                        id_cliente,
                        secrets.token_urlsafe(32),
                        productor.strip(),
                        sede,
                        patente,
                        telefono,
                        ip,
                    ),
                ).fetchone()
            except psycopg.errors.RaiseException as exc:
                if "limite_registros" in str(exc):
                    raise PermissionError("límite de cinco registros por hora") from exc
                raise
        return dict(fila)

    def autocompletar(self, patente: str) -> dict[str, str] | None:
        with self.conexion() as cn:
            fila = cn.execute(
                "SELECT * FROM fila.autocompletar_patente(%s)", (normalizar(patente),)
            ).fetchone()
        return dict(fila) if fila else None

    def ticket(self, ticket: str) -> dict[str, Any] | None:
        with self.conexion() as cn:
            fila = cn.execute("SELECT * FROM fila.leer_ticket(%s)", (ticket,)).fetchone()
        return dict(fila) if fila else None
