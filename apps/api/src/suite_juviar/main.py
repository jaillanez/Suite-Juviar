"""Un solo backend desplegable. Los routers se montan acá y en ningún otro lado."""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from suite_juviar.modulos.epp_analitica.api.app import tabla_de_errores as errores_analitica
from suite_juviar.modulos.legajo.api.app import tabla_de_errores as errores_legajo
from suite_juviar.modulos.recepcion.api.router import router as recepcion_router
from suite_juviar.modulos.rrhh_epp.api.mvp import crear_router as crear_rrhh_epp_router
from suite_juviar.modulos.rrhh_epp.api.mvp import tabla_de_errores as errores_rrhh_epp
from suite_juviar.modulos.rrhh_epp.mvp import construir as construir_rrhh_epp
from suite_juviar.modulos.salud.api.app import tabla_de_errores as errores_salud
from suite_juviar.modulos.turnos.api.app import tabla_de_errores as errores_turnos
from suite_juviar.plataforma.db.dsn import dsn_psycopg
from suite_juviar.plataforma.errores import registrar_manejadores
from suite_juviar.plataforma.identidad.api import router as identidad_router
from suite_juviar.plataforma.identidad.api.dependencias import (
    PERMISOS_POR_PERFIL,
    configurar_ingreso,
    configurar_recuperacion,
    configurar_subida,
    enviar_correo_interno,
    exigir_identidad_configurada,
    exigir_permiso,
    identidad_es_simulada,
)
from suite_juviar.plataforma.identidad.api.ingreso import router as ingreso_router
from suite_juviar.plataforma.identidad.api.ingreso import usuarios as usuarios_router
from suite_juviar.plataforma.identidad.api.subida import router as subida_router
from suite_juviar.plataforma.identidad.application.ingreso import ServicioIngreso
from suite_juviar.plataforma.identidad.application.recuperacion import ServicioRecuperacion
from suite_juviar.plataforma.identidad.application.subida_pin import ServicioSubidaPin
from suite_juviar.plataforma.identidad.infrastructure.recuperacion_sqlite import RecuperacionSQLite
from suite_juviar.plataforma.identidad.infrastructure.subida_sqlite import SubidaPinSQLite
from suite_juviar.plataforma.identidad.infrastructure.usuarios_sqlite import UsuariosSQLite
from suite_juviar.plataforma.terceros.api.contactos import configurar as configurar_contactos
from suite_juviar.plataforma.terceros.api.contactos import router as contactos_router
from suite_juviar.plataforma.terceros.api.conversaciones_bot import (
    router as conversaciones_bot_router,
)
from suite_juviar.plataforma.terceros.api.guardias import router as guardias_router
from suite_juviar.plataforma.terceros.api.ofertas_uva import router as ofertas_uva_router
from suite_juviar.plataforma.terceros.api.personal_bot import router as personal_bot_router
from suite_juviar.plataforma.terceros.api.sesion_organica import router as sesion_organica_router
from suite_juviar.plataforma.terceros.api.simulador_bot import router as simulador_bot_router
from suite_juviar.plataforma.terceros.api.tablero_fila import configurar as configurar_tablero_fila
from suite_juviar.plataforma.terceros.api.tablero_fila import recepcion as recepcion_datos_router
from suite_juviar.plataforma.terceros.api.tablero_fila import router as tablero_fila_router
from suite_juviar.plataforma.terceros.api.tablero_fila import turnos as turnos_bodega_router
from suite_juviar.plataforma.terceros.application.contactos import GestionarContactos
from suite_juviar.plataforma.terceros.infrastructure.contactos_postgres import (
    ContactosPostgreSQL,
)

from .composicion.olas_3_4_5 import construir_routers

entorno = os.getenv("SJ_ENTORNO") or os.getenv("ENTORNO") or "desarrollo"
exigir_identidad_configurada(entorno)
app = FastAPI(title="Suite Juviar", version="0.1.0")
registrar_manejadores(
    app,
    [*errores_rrhh_epp(), *errores_legajo(), *errores_salud(),
     *errores_turnos(), *errores_analitica()],
)

app.include_router(identidad_router, prefix="/api/v1")
if not identidad_es_simulada():
    ruta_usuarios = os.getenv("SJ_USUARIOS_SQLITE_PATH", "datos/usuarios.sqlite3")
    usuarios_sqlite = UsuariosSQLite(ruta_usuarios)
    configurar_ingreso(ServicioIngreso(usuarios_sqlite, frozenset(PERMISOS_POR_PERFIL)))
    # «¿Olvidaste tu contraseña?»: el correo sale desde la casilla de RRHH de Parámetros
    # (lo conecta composicion/olas_3_4_5.py) con un enlace a la dirección pública de Gestión.
    configurar_recuperacion(ServicioRecuperacion(
        usuarios_sqlite, RecuperacionSQLite(ruta_usuarios), enviar_correo_interno,
        os.getenv("SJ_URL_PUBLICA_GESTION", "").strip() or "https://juviar-enav.com.ar",
    ))
app.include_router(ingreso_router, prefix="/api/v1")
# Link personal + PIN para quien sólo sube facturas desde el celular (pantalla /subir).
configurar_subida(ServicioSubidaPin(
    SubidaPinSQLite(os.getenv("SJ_USUARIOS_SQLITE_PATH", "datos/usuarios.sqlite3"))
))
app.include_router(subida_router, prefix="/api/v1")
app.include_router(usuarios_router, prefix="/api/v1")
app.include_router(recepcion_router, prefix="/api/v1")
# En el servidor de Gestión, SJ_DATABASE_URL usa el rol terceros_gestor (sólo contactos de
# productores) por una red exclusiva con la base de la suite (infra/gestion/compose.yaml).
dsn_contactos = dsn_psycopg(obligatorio=False)
if dsn_contactos:
    configurar_contactos(
        GestionarContactos(
            ContactosPostgreSQL(dsn_contactos, os.getenv("RECEPCION_DSN_DMZ", "").strip())
        )
    )
app.include_router(contactos_router, prefix="/api/v1")
app.include_router(guardias_router, prefix="/api/v1")
configurar_tablero_fila(os.getenv("SJ_FILA_DSN_DMZ_LECTURA", "").strip())
app.include_router(tablero_fila_router, prefix="/api/v1")
app.include_router(recepcion_datos_router, prefix="/api/v1")
app.include_router(ofertas_uva_router, prefix="/api/v1")
app.include_router(sesion_organica_router, prefix="/api/v1")
app.include_router(turnos_bodega_router, prefix="/api/v1")
app.include_router(simulador_bot_router, prefix="/api/v1")
app.include_router(conversaciones_bot_router, prefix="/api/v1")
app.include_router(personal_bot_router, prefix="/api/v1")
rrhh_epp = construir_rrhh_epp()
app.include_router(crear_rrhh_epp_router(rrhh_epp), prefix="/api/v1/rrhh-epp")
for nombre, router in construir_routers(rrhh_epp).items():
    app.include_router(router, prefix=f"/api/v1/{nombre}")
# app.include_router(turnos_router, prefix="/api/v1")
# app.include_router(cosecha_router, prefix="/api/v1")


@app.get("/salud", dependencies=[Depends(exigir_permiso("suite.acceder"))])
async def salud() -> dict[str, str]:
    return {"estado": "ok"}


# En el servidor, la misma aplicación entrega las pantallas de Gestión ya compiladas.
estaticos = os.getenv("SJ_GESTION_ESTATICOS", "").strip()
if estaticos:
    app.mount("/", StaticFiles(directory=estaticos, html=True), name="gestion")
