from datetime import UTC, datetime
from uuid import uuid4

import pytest

from suite_juviar.modulos.seleccion.domain.modelos import (
    CampoExtraido,
    CVOriginal,
    ExtraccionCV,
    OrigenCV,
)
from suite_juviar.modulos.seleccion.infrastructure.postgres import (
    SeleccionPostgreSQL,
    datos_visibles_en_tabla,
)
from suite_juviar.plataforma.cripto.adaptador import ProtectorAESGCM


@pytest.mark.local
def test_postgres_conserva_original_y_extraccion_cifrados():
    dsn = "postgresql:///juviar_suite_local"
    protector = ProtectorAESGCM(b"h" * 32, b"c" * 32)
    repositorio = SeleccionPostgreSQL(dsn, protector)
    identificador = f"cv-local-{uuid4().hex}"
    ahora = datetime.now(UTC)
    original = CVOriginal(
        id=identificador,
        origen=OrigenCV.CORREO,
        referencia_fuente=f"correo:persona-{uuid4().hex}@example.test",
        nombre_archivo="Apellido-Nombre.pdf",
        contenido=b"%PDF contenido personal de prueba",
        sha256="a" * 64,
        recibido_en=ahora,
        incorporado_en=ahora,
    )
    assert repositorio.guardar_original(original) is True
    assert repositorio.guardar_original(original) is False
    assert repositorio.obtener_original(identificador) == original
    assert repositorio.existe_referencia(original.referencia_fuente) is True

    extraccion = ExtraccionCV(
        id_original=identificador,
        campos=(
            CampoExtraido(
                nombre="contacto",
                valor="persona@example.test",
                fragmento_fuente="Contacto: persona@example.test",
            ),
        ),
        campos_pendientes=("experiencia",),
        extraido_en=ahora,
    )
    repositorio.guardar_extraccion(extraccion)
    assert repositorio.obtener_extraccion(identificador) == extraccion

    visibles = datos_visibles_en_tabla(dsn, identificador)
    assert visibles is not None
    serializado = repr(visibles)
    assert "Apellido-Nombre" not in serializado
    assert "contenido personal" not in serializado
    assert "persona@example.test" not in serializado
    assert visibles["dueno_dato"] == "RRHH"
