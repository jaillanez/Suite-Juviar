from __future__ import annotations

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..busqueda import normalizar as normalizar_busqueda
from ..busqueda import terminos
from ..telefono import normalizar as normalizar_telefono
from .publicar_contactos import PublicadorContactos, encolar


class ContactosPostgreSQL:
    def __init__(self, dsn: str, dsn_dmz: str = "") -> None:
        self.dsn = dsn
        self.publicador = PublicadorContactos(dsn, dsn_dmz) if dsn_dmz else None

    def _publicar_ahora(self) -> None:
        if self.publicador:
            try:
                self.publicador.publicar()
            except psycopg.Error:
                pass

    def conectar(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    @staticmethod
    def _bloquear_contactos(cn, clientecuit: str) -> list[dict]:
        return cn.execute(
            """SELECT telefono,tareas FROM terceros.contacto_whatsapp
               WHERE clientecuit=%s AND activo ORDER BY telefono FOR UPDATE""",
            (clientecuit,),
        ).fetchall()

    @staticmethod
    def _exigir_otro_administrador(
        contactos: list[dict], telefono: str, tareas_nuevas: list[str] | None
    ) -> None:
        administradores = {
            contacto["telefono"]
            for contacto in contactos
            if "administrar_contactos" in contacto["tareas"]
        }
        if tareas_nuevas is not None and "administrar_contactos" in tareas_nuevas:
            administradores.add(telefono)
        else:
            administradores.discard(telefono)
        if not administradores:
            raise ValueError("no se puede dejar al productor sin administrador")

    def listar(self, clientecuit: str) -> list[dict]:
        with self.conectar() as cn:
            return [
                dict(f)
                for f in cn.execute(
                    """SELECT telefono,tareas,activo,origen,alta_por,alta_en
                       FROM terceros.contacto_whatsapp WHERE clientecuit=%s
                       ORDER BY activo DESC,telefono""",
                    (clientecuit,),
                ).fetchall()
            ]

    def eventos(self, clientecuit: str) -> list[dict]:
        with self.conectar() as cn:
            return [
                dict(f)
                for f in cn.execute(
                    """SELECT telefono,tipo,actor,antes,despues,detalle,momento
                       FROM terceros.contacto_evento WHERE clientecuit=%s
                       ORDER BY momento DESC LIMIT 100""",
                    (clientecuit,),
                ).fetchall()
            ]

    def alta(
        self, clientecuit: str, telefono: str, tareas: list[str], actor: str, motivo: str
    ) -> None:
        telefono = normalizar_telefono(telefono)
        with self.conectar() as cn:
            existente = cn.execute(
                """SELECT activo,tareas FROM terceros.contacto_whatsapp
                   WHERE clientecuit=%s AND telefono=%s FOR UPDATE""",
                (clientecuit, telefono),
            ).fetchone()
            if existente and existente["activo"]:
                raise ValueError("el contacto ya existe y está activo")
            cn.execute(
                """INSERT INTO terceros.contacto_whatsapp
                   (telefono,clientecuit,tareas,origen,alta_por,activo)
                   VALUES (%s,%s,%s,'alta_manual',%s,true)
                   ON CONFLICT (telefono,clientecuit) DO UPDATE SET
                     tareas=EXCLUDED.tareas,activo=true,origen='alta_manual',
                     alta_por=EXCLUDED.alta_por,alta_en=now()""",
                (telefono, clientecuit, tareas, actor),
            )
            tipo = "alta_reactivada" if existente else "alta"
            cn.execute(
                """INSERT INTO terceros.contacto_evento
                   (clientecuit,telefono,tipo,actor,antes,despues,detalle)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (
                    clientecuit,
                    telefono,
                    tipo,
                    actor,
                    existente["tareas"] if existente else None,
                    tareas,
                    Jsonb({"motivo": motivo}),
                ),
            )
            encolar(cn, clientecuit, telefono)
        self._publicar_ahora()

    def pendientes(self) -> list[dict]:
        with self.conectar() as cn:
            filas = cn.execute(
                """SELECT p.*,
                          (SELECT count(*) FROM recepcion.descarga d
                           WHERE d.clienterazonsocial ILIKE '%%'||p.nombre_excel||'%%') entregas
                   FROM terceros.contacto_pendiente p
                   WHERE p.estado='pendiente'
                   ORDER BY entregas DESC,p.id"""
            ).fetchall()
        return [dict(f) for f in filas]

    def buscar_productores(self, consulta: str) -> list[dict]:
        palabras = terminos(consulta)
        if not palabras:
            return []
        patron = "%" + "%".join(palabras) + "%"
        codigo = normalizar_busqueda(consulta)
        with self.conectar() as cn:
            filas = cn.execute(
                """SELECT clientecuit,max(clienterazonsocial) razonsocial,
                          array_agg(DISTINCT clientecodigo) codigos,max(fecha)::date ultima_entrega
                   FROM recepcion.descarga
                   WHERE clientecuit IS NOT NULL AND estado<>'ausente_en_origen'
                     AND (upper(translate(clienterazonsocial,'ÁÉÍÓÚÜÑ','AEIOUUN')) LIKE %s
                          OR clientecodigo=%s)
                   GROUP BY clientecuit ORDER BY ultima_entrega DESC NULLS LAST LIMIT 20""",
                (patron, codigo),
            ).fetchall()
        return [dict(f) for f in filas]

    def resolver_pendiente(
        self,
        pendiente_id: int,
        clientecuit: str,
        tareas: set[str],
        actor: str,
        motivo: str,
    ) -> None:
        from ..domain.permisos import validar_tareas

        with self.conectar() as cn:
            pendiente = cn.execute(
                """SELECT * FROM terceros.contacto_pendiente
                   WHERE id=%s AND estado='pendiente' FOR UPDATE""",
                (pendiente_id,),
            ).fetchone()
            if not pendiente:
                raise ValueError("pendiente inexistente o ya resuelto")
            telefono = normalizar_telefono(pendiente["telefono"] or pendiente["telefono_crudo"])
        self.alta(clientecuit, telefono, sorted(validar_tareas(tareas)), actor, motivo)
        with self.conectar() as cn:
            cn.execute(
                """UPDATE terceros.contacto_pendiente SET estado='resuelto',
                          resuelto_por=%s,resuelto_en=now(),clientecuit=%s,telefono=%s,nota=%s
                   WHERE id=%s AND estado='pendiente'""",
                (actor, clientecuit, telefono, motivo, pendiente_id),
            )

    def descartar_pendiente(self, pendiente_id: int, actor: str, nota: str) -> None:
        with self.conectar() as cn:
            fila = cn.execute(
                """UPDATE terceros.contacto_pendiente SET estado='descartado',
                          resuelto_por=%s,resuelto_en=now(),nota=%s
                   WHERE id=%s AND estado='pendiente' RETURNING id""",
                (actor, nota, pendiente_id),
            ).fetchone()
            if not fila:
                raise ValueError("pendiente inexistente o ya resuelto")

    def guardar_tareas(self, clientecuit: str, telefono: str, tareas: list[str], actor: str) -> None:
        with self.conectar() as cn:
            contactos = self._bloquear_contactos(cn, clientecuit)
            antes = next((c for c in contactos if c["telefono"] == telefono), None)
            if not antes:
                raise ValueError("contacto activo inexistente")
            self._exigir_otro_administrador(contactos, telefono, tareas)
            cn.execute(
                """UPDATE terceros.contacto_whatsapp SET tareas=%s
                   WHERE clientecuit=%s AND telefono=%s""",
                (tareas, clientecuit, telefono),
            )
            cn.execute(
                """INSERT INTO terceros.contacto_evento
                   (clientecuit,telefono,tipo,actor,antes,despues)
                   VALUES (%s,%s,'permisos_cambiados',%s,%s,%s)""",
                (clientecuit, telefono, actor, antes["tareas"], tareas),
            )
            encolar(cn, clientecuit, telefono)
        self._publicar_ahora()

    def baja(self, clientecuit: str, telefono: str, actor: str, motivo: str) -> None:
        with self.conectar() as cn:
            contactos = self._bloquear_contactos(cn, clientecuit)
            antes = next((c for c in contactos if c["telefono"] == telefono), None)
            if not antes:
                raise ValueError("contacto activo inexistente")
            self._exigir_otro_administrador(contactos, telefono, None)
            cn.execute(
                """UPDATE terceros.contacto_whatsapp SET activo=false
                   WHERE clientecuit=%s AND telefono=%s""",
                (clientecuit, telefono),
            )
            cn.execute(
                """INSERT INTO terceros.contacto_evento
                   (clientecuit,telefono,tipo,actor,antes,detalle)
                   VALUES (%s,%s,'baja',%s,%s,%s)""",
                (clientecuit, telefono, actor, antes["tareas"], Jsonb({"motivo": motivo})),
            )
            encolar(cn, clientecuit, telefono)
        self._publicar_ahora()

    def reemplazar(self, clientecuit: str, anterior: str, nuevo: str, actor: str, motivo: str) -> None:
        tareas_admin = ["ver_informes", "pedir_turnos", "administrar_contactos"]
        with self.conectar() as cn:
            contactos = self._bloquear_contactos(cn, clientecuit)
            viejo = next((c for c in contactos if c["telefono"] == anterior), None)
            if not viejo or "administrar_contactos" not in viejo["tareas"]:
                raise ValueError("el contacto anterior no es administrador activo")
            cn.execute(
                """INSERT INTO terceros.contacto_whatsapp
                   (telefono,clientecuit,tareas,origen,alta_por,activo)
                   VALUES (%s,%s,%s,'alta_manual',%s,true)
                   ON CONFLICT (telefono,clientecuit) DO UPDATE
                     SET tareas=EXCLUDED.tareas,activo=true,origen='alta_manual',alta_por=EXCLUDED.alta_por""",
                (nuevo, clientecuit, tareas_admin, actor),
            )
            cn.execute(
                """UPDATE terceros.contacto_whatsapp SET activo=false
                   WHERE clientecuit=%s AND telefono=%s""",
                (clientecuit, anterior),
            )
            detalle = Jsonb({"anterior": anterior, "nuevo": nuevo, "motivo": motivo})
            cn.execute(
                """INSERT INTO terceros.contacto_evento
                   (clientecuit,telefono,tipo,actor,antes,despues,detalle)
                   VALUES (%s,%s,'reemplazo_administrador',%s,%s,%s,%s)""",
                (clientecuit, nuevo, actor, viejo["tareas"], tareas_admin, detalle),
            )
            encolar(cn, clientecuit, anterior)
            encolar(cn, clientecuit, nuevo)
        self._publicar_ahora()
