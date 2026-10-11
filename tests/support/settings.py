from typing import Any

from advocondo.config import Settings
from tests.support.environment import env_example_variables


def env_example_values() -> dict[str, str]:
    """Every variable of the .env.example, keyed by the Settings field name."""
    return {
        name.lower(): value
        for name, value in env_example_variables().items()
        if name.lower() in Settings.model_fields
    }


def make_settings(
    *, read_from_environment: tuple[str, ...] = (), **overrides: Any
) -> Settings:
    """Settings from the .env.example plus the overrides, ignoring the local .env and
    the process environment, so tests do not depend on the developer's machine.

    `read_from_environment` names the fields left for the environment, for tests
    that set an environment variable themselves.
    """
    values = env_example_values() | overrides
    for field_name in read_from_environment:
        values.pop(field_name)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]
