import os

from consulta_publica.api.descargas import cargar_clave, obtener_repositorio
from consulta_publica.api.descargas import router as descargas_router
from consulta_publica.api.router import router
from consulta_publica.lectura.repositorio_descargas import RepositorioDescargasPg
from fastapi import FastAPI

cargar_clave()
dsn_lector = os.environ.get("CONSULTA_DSN_LECTOR", "").strip()
if not dsn_lector:
    raise RuntimeError("Falta la variable de entorno CONSULTA_DSN_LECTOR")
repositorio_descargas = RepositorioDescargasPg(dsn_lector)

app = FastAPI(title="Consulta pública Suite Juviar", version="0.1.0")
app.include_router(router)
app.include_router(descargas_router)
app.dependency_overrides[obtener_repositorio] = lambda: repositorio_descargas
