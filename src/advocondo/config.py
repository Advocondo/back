from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração lida das variáveis de ambiente (e do .env, em dev)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Opcional para que a API suba (e /health responda) mesmo sem banco configurado.
    database_url: str | None = None

    # Observabilidade (ver docs/observabilidade.md)
    environment: str = "local"
    release: str | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
