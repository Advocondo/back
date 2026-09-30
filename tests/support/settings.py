from typing import Any

from advocondo.config import Settings


def make_settings(**overrides: Any) -> Settings:
    """Settings só com os valores passados, sem ler o .env local."""
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]
