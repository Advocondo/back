"""Ambiente do Alembic. Ver docs/migrations.md."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from advocondo import models  # noqa: F401  (registra os modelos em Base.metadata)
from advocondo.config import get_settings
from advocondo.db import Base

config = context.config
if config.config_file_name is not None:
    # Preserva a configuração de logs da aplicação (JSON) ao rodar dentro dela.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    # `sqlalchemy.url` explícito (testes) tem prioridade sobre a DATABASE_URL.
    url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL não está definida.")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
