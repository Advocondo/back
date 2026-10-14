from alembic import context
from sqlalchemy import engine_from_config, pool

import advocondo.models  # noqa: F401  # registers every model in Base.metadata
from advocondo.config import get_settings
from advocondo.db import Base
from advocondo.logging_config import configure_logging

config = context.config
target_metadata = Base.metadata

# Callers such as the migration tests set the URL themselves; otherwise use the app's.
if not config.get_main_option("sqlalchemy.url"):
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set.")
    config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
