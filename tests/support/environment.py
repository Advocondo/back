"""Fills the variables missing from the environment with the .env.example values,
before the app is imported (it reads the settings on import).

Variables already in the environment win: in the API container they come from the
.env through docker-compose, and in the CI the workflow sets TEST_DATABASE_URL.
"""

import os
from pathlib import Path

from dotenv import dotenv_values

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def env_example_variables() -> dict[str, str]:
    return {name: value or "" for name, value in dotenv_values(ENV_EXAMPLE).items()}


def fill_missing_environment() -> None:
    for name, value in env_example_variables().items():
        os.environ.setdefault(name, value)
