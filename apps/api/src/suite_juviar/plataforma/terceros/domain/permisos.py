"""Reglas puras de permisos de los contactos del productor."""

VER_INFORMES = "ver_informes"
PEDIR_TURNOS = "pedir_turnos"
ADMINISTRAR_CONTACTOS = "administrar_contactos"
TAREAS = frozenset({VER_INFORMES, PEDIR_TURNOS, ADMINISTRAR_CONTACTOS})


class PermisoInvalido(ValueError):
    pass


def validar_tareas(tareas: set[str] | frozenset[str]) -> frozenset[str]:
    normalizadas = frozenset(tareas)
    if not normalizadas:
        raise PermisoInvalido("un contacto tiene que tener al menos una tarea")
    if not normalizadas <= TAREAS:
        raise PermisoInvalido(f"tareas desconocidas: {sorted(normalizadas - TAREAS)}")
    return normalizadas


def validar_cambio(
    contactos_activos: dict[str, frozenset[str]],
    telefono: str,
    nuevas: frozenset[str] | None,
) -> None:
    despues = dict(contactos_activos)
    if nuevas is None:
        despues.pop(telefono, None)
    else:
        despues[telefono] = validar_tareas(nuevas)
    if not any(ADMINISTRAR_CONTACTOS in tareas for tareas in despues.values()):
        raise PermisoInvalido("no se puede dejar al productor sin administrador")
