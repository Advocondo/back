"""Migrations must build exactly the schema the models describe, and be reversible."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.engine import URL

import advocondo.models  # noqa: F401
from advocondo.db import Base
from tests.support.database import ensure_database_exists, get_test_database_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def migrations_url() -> URL:
    # A database of its own: the suite's test database is built from the models.
    url = get_test_database_url().set(database="advocondo_migrations_test")
    ensure_database_exists(url)
    return url


@pytest.fixture(scope="module")
def migrations_engine(migrations_url: URL) -> Iterator[Engine]:
    engine = create_engine(migrations_url)
    yield engine
    engine.dispose()


@pytest.fixture
def alembic_config(migrations_url: URL) -> Iterator[Config]:
    config = Config(PROJECT_ROOT / "alembic.ini")
    config.set_main_option(
        "sqlalchemy.url", migrations_url.render_as_string(hide_password=False)
    )
    command.downgrade(config, "base")
    yield config
    command.downgrade(config, "base")


def test_upgrade_builds_the_schema_described_by_the_models(
    alembic_config: Config, migrations_engine: Engine
) -> None:
    command.upgrade(alembic_config, "head")

    with migrations_engine.connect() as connection:
        differences = compare_metadata(
            MigrationContext.configure(connection), Base.metadata
        )

    assert differences == []


def test_downgrade_removes_every_table(
    alembic_config: Config, migrations_engine: Engine
) -> None:
    command.upgrade(alembic_config, "head")

    command.downgrade(alembic_config, "base")

    assert inspect(migrations_engine).get_table_names() == ["alembic_version"]
