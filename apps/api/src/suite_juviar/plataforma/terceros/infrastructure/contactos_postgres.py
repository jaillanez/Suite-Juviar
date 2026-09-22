from __future__ import annotations

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class ContactosPostgreSQL:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

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
