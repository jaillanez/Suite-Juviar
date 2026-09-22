from __future__ import annotations

from typing import Protocol

from suite_juviar.plataforma.terceros.domain.permisos import (
    TAREAS,
    validar_cambio,
    validar_tareas,
)


class Contactos(Protocol):
    def listar(self, clientecuit: str) -> list[dict]: ...
    def eventos(self, clientecuit: str) -> list[dict]: ...
    def guardar_tareas(self, clientecuit: str, telefono: str, tareas: list[str], actor: str) -> None: ...
    def baja(self, clientecuit: str, telefono: str, actor: str, motivo: str) -> None: ...
    def reemplazar(self, clientecuit: str, anterior: str, nuevo: str, actor: str, motivo: str) -> None: ...
    def alta(self, clientecuit: str, telefono: str, tareas: list[str], actor: str, motivo: str) -> None: ...
    def pendientes(self) -> list[dict]: ...
    def descartar_pendiente(self, pendiente_id: int, actor: str, nota: str) -> None: ...
    def buscar_productores(self, consulta: str) -> list[dict]: ...


class GestionarContactos:
    def __init__(self, repo: Contactos) -> None:
        self.repo = repo

    def listar(self, clientecuit: str) -> dict:
        return {
            "contactos": self.repo.listar(clientecuit),
            "eventos": self.repo.eventos(clientecuit),
            "tareas_disponibles": sorted(TAREAS),
        }

    def tareas(self, clientecuit: str, telefono: str, tareas: set[str], actor: str) -> None:
        nuevas = validar_tareas(tareas)
        actuales = {
            c["telefono"]: frozenset(c["tareas"])
            for c in self.repo.listar(clientecuit)
            if c["activo"]
        }
        validar_cambio(actuales, telefono, nuevas)
        self.repo.guardar_tareas(clientecuit, telefono, sorted(nuevas), actor)

    def alta(
        self, clientecuit: str, telefono: str, tareas: set[str], actor: str, motivo: str
    ) -> None:
        from suite_juviar.plataforma.terceros.telefono import normalizar

        nuevas = validar_tareas(tareas)
        self.repo.alta(
            clientecuit, normalizar(telefono), sorted(nuevas), actor, motivo.strip()
        )

    def pendientes(self) -> list[dict]:
        return self.repo.pendientes()

    def descartar_pendiente(self, pendiente_id: int, actor: str, nota: str) -> None:
        self.repo.descartar_pendiente(pendiente_id, actor, nota.strip())

    def buscar_productores(self, consulta: str) -> list[dict]:
        return self.repo.buscar_productores(consulta)

    def dar_baja(self, clientecuit: str, telefono: str, actor: str, motivo: str) -> None:
        actuales = {
            c["telefono"]: frozenset(c["tareas"])
            for c in self.repo.listar(clientecuit)
            if c["activo"]
        }
        validar_cambio(actuales, telefono, None)
        self.repo.baja(clientecuit, telefono, actor, motivo)

    def reemplazar(
        self, clientecuit: str, anterior: str, nuevo: str, actor: str, motivo: str
    ) -> None:
        if anterior == nuevo:
            raise ValueError("el teléfono nuevo debe ser distinto")
        if not motivo.strip():
            raise ValueError("el reemplazo exige un motivo")
        self.repo.reemplazar(clientecuit, anterior, nuevo, actor, motivo.strip())
