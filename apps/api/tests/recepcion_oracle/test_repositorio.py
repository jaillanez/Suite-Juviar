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


class ConexionDmzFalsa(ConexionFalsa):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def test_publica_cuenta_patente_y_cuit_normalizados(monkeypatch) -> None:
    """infra/044: el bot identifica la cuenta por la patente o el CUIT tal como los escriben."""
    from suite_juviar.modulos.recepcion.integracion_oracle import repositorio

    conexion = ConexionDmzFalsa()
    monkeypatch.setattr(repositorio.psycopg, "connect", lambda *_a, **_k: conexion)
    fila = {"id": 1, "sede": "chimbas", "ciu": "17377", "id_origen": "9", "fecha": None,
            "nroinscripto": "J81000", "clientecuit": "20227149583", "clientecodigo": " J80158 ",
            "codigotransporte": "vct-917", "cuit": "20-22714958-3", "neto": 1000,
            "descvariedad": "MALBEC", "azucar": None, "estado": "descargado", "actualizado_en": None}

    repositorio.RepositorioDmz("dsn").publicar([fila])

    [[publicada]] = conexion.cursores[0].lotes
    assert (publicada["clientecodigo"], publicada["patente"], publicada["cuit_inscripto"]) == (
        "J80158", "VCT917", "20227149583")
    assert repositorio.normalizar_patente("AB 123 CD") == "AB123CD"
    assert repositorio.normalizar_patente("x") is None
