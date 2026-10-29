"""Crea el primer usuario de Gestión desde la consola del servidor.

    python -m suite_juviar.plataforma.identidad.api.consola correo@empresa "Nombre" SUPERADMIN ENAV

La contraseña se pide sin mostrarla en pantalla. Los demás usuarios se crean
desde la pantalla Usuarios de Gestión.
"""

from __future__ import annotations

import getpass
import os
import sys

from ..application.ingreso import ServicioIngreso
from ..domain.usuarios import DatosDeUsuarioInvalidos
from ..infrastructure.usuarios_sqlite import UsuariosSQLite
from .dependencias import PERMISOS_POR_PERFIL


def principal(argumentos: list[str]) -> int:
    if len(argumentos) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    email, nombre, perfil, empresa = argumentos
    ruta = os.getenv("SJ_USUARIOS_SQLITE_PATH", "datos/usuarios.sqlite3")
    servicio = ServicioIngreso(UsuariosSQLite(ruta), frozenset(PERMISOS_POR_PERFIL))
    clave = getpass.getpass("Contraseña: ")
    if clave != getpass.getpass("Repetila: "):
        print("Las contraseñas no coinciden.", file=sys.stderr)
        return 1
    try:
        usuario = servicio.crear_usuario("consola", email, nombre, perfil, empresa, clave)
    except DatosDeUsuarioInvalidos as exc:
        print(exc, file=sys.stderr)
        return 1
    # El primer usuario elige su contraseña acá: no hace falta forzar el cambio.
    servicio.repositorio.cambiar_clave(
        usuario.id, servicio.repositorio.obtener_por_email(usuario.email)[1], debe_cambiar=False
    )
    print(f"Usuario creado: {usuario.email} ({usuario.perfil}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal(sys.argv[1:]))
