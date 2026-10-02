"""As migrations precisam descrever exatamente os modelos (sem divergência)."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine

from advocondo.db import Base


def test_migrations_batem_com_os_modelos(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []
