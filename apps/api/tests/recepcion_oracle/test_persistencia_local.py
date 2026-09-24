import asyncio
import sqlite3
from decimal import Decimal

from suite_juviar.modulos.recepcion.application.casos_uso import DatosIngreso
from suite_juviar.modulos.recepcion.domain.entidades import OrigenPeso
from suite_juviar.modulos.recepcion.infrastructure.persistencia_local import (
    AbrirRomaneoSQLite,
)


def test_romaneo_local_persiste_estado_outbox_y_auditoria(tmp_path):
    ruta = tmp_path / "recepcion.sqlite3"
    datos = DatosIngreso(
        productor_cuit="20123456789", transportista_cuit="20987654321",
        chofer_dni="30111222", patente_chasis="AA123BB", patente_acoplado=None,
        variedad="Malbec", finca="Finca Norte", bruto_kg=Decimal(15000),
        origen_peso=OrigenPeso.BASCULA_DIGITAL, operador_legajo="1210",
    )

    primero = asyncio.run(AbrirRomaneoSQLite(ruta)(datos))
    segundo = asyncio.run(AbrirRomaneoSQLite(ruta)(datos))

    assert (primero.numero, segundo.numero) == (1, 2)
    with sqlite3.connect(ruta) as cn:
        assert cn.execute("SELECT count(*) FROM romaneo").fetchone()[0] == 2
        assert cn.execute("SELECT count(*) FROM outbox").fetchone()[0] == 2
        assert cn.execute("SELECT count(*) FROM auditoria").fetchone()[0] == 2
