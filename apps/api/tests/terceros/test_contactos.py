import pytest

from suite_juviar.plataforma.terceros.application.contactos import GestionarContactos
from suite_juviar.plataforma.terceros.infrastructure.contactos_postgres import (
    ContactosPostgreSQL,
)

ADMIN = ["ver_informes", "pedir_turnos", "administrar_contactos"]


class Repo:
    def __init__(self):
        self.contactos = [
            {"telefono": "5491", "tareas": ADMIN, "activo": True},
            {"telefono": "5492", "tareas": ["ver_informes"], "activo": True},
        ]
        self.operaciones = []

    def listar(self, _): return list(self.contactos)
    def eventos(self, _): return []
    def guardar_tareas(self, *args): self.operaciones.append(("tareas", args))
    def baja(self, *args): self.operaciones.append(("baja", args))
    def reemplazar(self, *args): self.operaciones.append(("reemplazo", args))


def test_no_deja_quitar_la_administracion_al_ultimo_admin():
    servicio = GestionarContactos(Repo())
    with pytest.raises(ValueError):
        servicio.tareas("20-1", "5491", {"ver_informes"}, "bodega")


def test_reemplazo_exige_numero_distinto_y_motivo():
    servicio = GestionarContactos(Repo())
    with pytest.raises(ValueError):
        servicio.reemplazar("20-1", "5491", "5491", "bodega", "cambio")
    with pytest.raises(ValueError):
        servicio.reemplazar("20-1", "5491", "5493", "bodega", " ")


def test_reemplazo_delega_una_operacion_atomica():
    repo = Repo()
    GestionarContactos(repo).reemplazar("20-1", "5491", "5493", "bodega", "perdió teléfono")
    assert repo.operaciones == [
        ("reemplazo", ("20-1", "5491", "5493", "bodega", "perdió teléfono"))
    ]


def test_repositorio_tambien_protege_al_ultimo_admin_bajo_bloqueo():
    contactos = [{"telefono": "5491", "tareas": ADMIN}]
    with pytest.raises(ValueError, match="sin administrador"):
        ContactosPostgreSQL._exigir_otro_administrador(
            contactos, "5491", ["ver_informes"]
        )
