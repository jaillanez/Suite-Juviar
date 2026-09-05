from consulta_publica.api.router import router
from fastapi import FastAPI

app = FastAPI(title="Consulta pública Suite Juviar", version="0.1.0")
app.include_router(router)
