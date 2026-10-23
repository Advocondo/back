import re
from datetime import timedelta
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

MIN_SETUP_TOKEN_LENGTH = 32


class Settings(BaseSettings):
    """Configuração lida das variáveis de ambiente (e do .env, em dev)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    environment: str
    release: str | None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    log_format: Literal["json", "console"]
    sentry_dsn: str | None
    sentry_traces_sample_rate: float

    cors_allow_origins: Annotated[list[str], NoDecode]
    cors_allow_origin_regex: str | None
    cors_allow_credentials: bool
    hsts_max_age: int

    session_duration_hours: int
    remembered_session_duration_days: int

    setup_token: str | None

    frontend_url: str
    password_reset_link_minutes: int
    password_reset_max_requests: int
    password_reset_request_window_minutes: int

    invite_link_minutes: int

    landing_image_max_kilobytes: int

    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_use_tls: bool
    email_from: str | None

    @field_validator(
        "release",
        "sentry_dsn",
        "cors_allow_origin_regex",
        "setup_token",
        "smtp_host",
        "smtp_username",
        "smtp_password",
        "email_from",
        mode="before",
    )
    @classmethod
    def _empty_as_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def session_duration(self) -> timedelta:
        return timedelta(hours=self.session_duration_hours)

    @property
    def remembered_session_duration(self) -> timedelta:
        return timedelta(days=self.remembered_session_duration_days)

    @property
    def password_reset_link_duration(self) -> timedelta:
        return timedelta(minutes=self.password_reset_link_minutes)

    @property
    def password_reset_request_window(self) -> timedelta:
        return timedelta(minutes=self.password_reset_request_window_minutes)

    @property
    def invite_link_duration(self) -> timedelta:
        return timedelta(minutes=self.invite_link_minutes)

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
    return Settings()  # type: ignore[call-arg]
