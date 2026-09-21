from contextlib import nullcontext

from suite_juviar.modulos.recepcion.integracion_oracle.modelo import ClaveDescarga
from suite_juviar.modulos.recepcion.integracion_oracle.planificador import Plan
from suite_juviar.modulos.recepcion.integracion_oracle.repositorio import RepositorioSuite


class CursorFalso:
    def __init__(self) -> None:
        self.lotes: list[list[tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def executemany(self, sql: str, parametros: list[tuple]) -> None:
        assert "id_origen" in sql
        self.lotes.append(parametros)


class ConexionFalsa:
    def __init__(self) -> None:
        self.cursores: list[CursorFalso] = []

    def transaction(self):
        return nullcontext()

    def cursor(self) -> CursorFalso:
        cursor = CursorFalso()
        self.cursores.append(cursor)
        return cursor


def test_actualiza_sin_cambio_y_ausencias_con_cursor() -> None:
    conexion = ConexionFalsa()
    plan = Plan(
        sin_cambio=[ClaveDescarga("1", "A")],
        ausentes=[ClaveDescarga("2", "B")],
    )

    RepositorioSuite.aplicar(conexion, "chimbas", plan)  # type: ignore[arg-type]

    assert conexion.cursores[0].lotes == [[("chimbas", "1", "A")]]
    assert conexion.cursores[1].lotes == [[("ausente_en_origen", "chimbas", "2", "B")]]
