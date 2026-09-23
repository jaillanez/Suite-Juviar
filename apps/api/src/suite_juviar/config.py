from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SJ_")

    entorno: str = "dev"

    # La conexión se resuelve exclusivamente en plataforma/db/dsn.py.
    redis_url: str = "redis://localhost:6379/0"

    # Clave del HMAC de datos personales. Fuera de la base, inyectada por el
    # orquestador. Si falta, la app no arranca: no hay fallback silencioso.
    hmac_datos_personales: str = Field(min_length=32)
    clave_cifrado_datos_personales: str = Field(min_length=32)

    # VPN al servidor de Nexus (Santa Fe). Pendiente: credenciales (§4.4).
    nexus_dsn: str = ""


@lru_cache
def _cargar() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = _cargar()
