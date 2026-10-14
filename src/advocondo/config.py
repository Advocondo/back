import re
from datetime import timedelta
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Long enough that guessing it is not practical; `openssl rand -hex 32` gives 64.
MIN_SETUP_TOKEN_LENGTH = 32


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

    # CORS e HTTPS (ver docs/https-cors.md). Sem configuração, nenhuma origem
    # externa é liberada.
    cors_allow_origins: Annotated[list[str], NoDecode] = []
    cors_allow_origin_regex: str | None = None
    cors_allow_credentials: bool = False
    hsts_max_age: int = 0

    # Login (ver docs/auth.md)
    session_duration_hours: int = 12
    remembered_session_duration_days: int = 30

    # Criação do primeiro Administrador por POST /setup (ver docs/auth.md).
    # Vazio = rota desligada.
    setup_token: str | None = None

    @property
    def session_duration(self) -> timedelta:
        return timedelta(hours=self.session_duration_hours)

    @property
    def remembered_session_duration(self) -> timedelta:
        return timedelta(days=self.remembered_session_duration_days)

    @field_validator("setup_token")
    @classmethod
    def _strong_setup_token(cls, token: str | None) -> str | None:
        if token and len(token) < MIN_SETUP_TOKEN_LENGTH:
            raise ValueError(
                f"SETUP_TOKEN precisa ter pelo menos {MIN_SETUP_TOKEN_LENGTH} caracteres."
            )
        return token or None

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        # Aceita "https://a.com,https://b.com" na variável de ambiente.
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_allow_origins")
    @classmethod
    def _no_wildcard(cls, origins: list[str]) -> list[str]:
        if "*" in origins:
            raise ValueError("CORS_ALLOW_ORIGINS não pode ser '*'; liste os domínios.")
        return [origin.rstrip("/") for origin in origins]

    @field_validator("cors_allow_origin_regex")
    @classmethod
    def _valid_regex(cls, pattern: str | None) -> str | None:
        if pattern:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"CORS_ALLOW_ORIGIN_REGEX inválida: {exc}") from exc
        return pattern or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
