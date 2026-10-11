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

    database_url: str

    # Observabilidade (ver docs/observabilidade.md)
    environment: str
    release: str | None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    log_format: Literal["json", "console"]
    sentry_dsn: str | None
    sentry_traces_sample_rate: float

    # CORS e HTTPS (ver docs/https-cors.md). Lista vazia: nenhuma origem externa.
    cors_allow_origins: Annotated[list[str], NoDecode]
    cors_allow_origin_regex: str | None
    cors_allow_credentials: bool
    hsts_max_age: int

    # Login (ver docs/auth.md)
    session_duration_hours: int
    remembered_session_duration_days: int

    # Criação do primeiro Administrador por POST /setup (ver docs/auth.md).
    # Vazio = rota desligada.
    setup_token: str | None

    @field_validator(
        "release",
        "sentry_dsn",
        "cors_allow_origin_regex",
        "setup_token",
        mode="before",
    )
    @classmethod
    def _empty_as_none(cls, value: object) -> object:
        # "SENTRY_DSN=" no ambiente quer dizer "desligado", não um DSN vazio.
        if isinstance(value, str) and not value.strip():
            return None
        return value

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
        return token

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
        return pattern


@lru_cache
def get_settings() -> Settings:
    # The fields come from the environment, which mypy cannot see.
    return Settings()  # type: ignore[call-arg]
