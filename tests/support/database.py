"""Utilitários do banco de testes."""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url


def get_test_database_url() -> URL:
    """Lida de TEST_DATABASE_URL, que o docker-compose e o CI definem."""
    raw_url = os.environ.get("TEST_DATABASE_URL")
    if not raw_url:
        raise RuntimeError(
            "TEST_DATABASE_URL não está definida. Rode os testes pelo container: "
            "docker compose exec api uv run pytest"
        )
    url = make_url(raw_url)
    assert_is_test_database(url)
    return url


def assert_is_test_database(url: URL) -> None:
    """Impede que os testes rodem (e apaguem dados) fora de um banco de testes."""
    if not url.database or not url.database.endswith("_test"):
        raise ValueError(
            f"TEST_DATABASE_URL deve apontar para um banco terminado em '_test', "
            f"não para {url.database!r}."
        )


def ensure_database_exists(url: URL) -> None:
    """Cria o banco de testes na primeira execução, se ainda não existir."""
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": url.database},
            )
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        admin.dispose()
