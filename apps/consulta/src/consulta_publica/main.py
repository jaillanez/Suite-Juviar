import os

from consulta_publica.api.archivos import configurar as configurar_archivos
from consulta_publica.api.archivos import router as archivos_router
from consulta_publica.api.descargas import cargar_clave, obtener_repositorio
from consulta_publica.api.descargas import router as descargas_router
from consulta_publica.api.router import router
from consulta_publica.bot import webhook
from consulta_publica.bot.repositorio import RepositorioArchivos, RepositorioWebhook
from consulta_publica.lectura.repositorio_descargas import RepositorioDescargasPg
from fastapi import FastAPI

cargar_clave()
webhook.cargar_secreto()
dsn_lector = os.environ.get("CONSULTA_DSN_LECTOR", "").strip()
if not dsn_lector:
    raise RuntimeError("Falta la variable de entorno CONSULTA_DSN_LECTOR")
repositorio_descargas = RepositorioDescargasPg(dsn_lector)
dsn_webhook = os.environ.get("BOT_WEBHOOK_DSN", "").strip()
if not dsn_webhook:
    raise RuntimeError("Falta la variable de entorno BOT_WEBHOOK_DSN")
repositorio_webhook = RepositorioWebhook(dsn_webhook)
dsn_archivos = os.environ.get("BOT_ARCHIVOS_DSN", "").strip()
if not dsn_archivos:
    raise RuntimeError("Falta la variable de entorno BOT_ARCHIVOS_DSN")
configurar_archivos(RepositorioArchivos(dsn_archivos))

app = FastAPI(title="Consulta pública Suite Juviar", version="0.1.0")
app.include_router(router)
app.include_router(descargas_router)
app.include_router(webhook.router)
app.include_router(archivos_router)
app.dependency_overrides[obtener_repositorio] = lambda: repositorio_descargas
app.dependency_overrides[webhook.obtener_cola] = lambda: repositorio_webhook
