"""Fixtures compartilhadas por todos os testes. Ver docs/testes.md."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

# Fills the missing environment variables before the app reads its settings on import.
import tests  # noqa: F401
from advocondo.config import Settings, get_settings
from advocondo.db import Base, get_session
from advocondo.main import app
from tests.support.clock import FrozenClock
from tests.support.database import ensure_database_exists, get_test_database_url
from tests.support.email import Outbox
from tests.support.settings import make_settings

pytest_plugins = [
    "tests.fixtures.users",
    "tests.fixtures.auth",
    "tests.fixtures.email",
    "tests.fixtures.condominios",
    "tests.fixtures.devedores",
]

# Fixtures que precisam do Postgres de teste; quem as usa vira teste de integração.
DB_FIXTURES = {"db_session", "db_client"}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if DB_FIXTURES & set(getattr(item, "fixturenames", ())):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    """Banco de testes isolado, com o schema recriado a cada execução da suíte."""
    url = get_test_database_url()
    ensure_database_exists(url)
    engine = create_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """Sessão cujo conteúdo é descartado ao fim de cada teste.

    Tudo roda dentro de uma transação que sofre rollback no final; os
    `commit()` do código testado viram savepoints dentro dela.
    """
    with db_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def client() -> TestClient:
    """Cliente HTTP da API, sem banco de dados."""
    return TestClient(app)


@pytest.fixture
def settings() -> Settings:
    """Configuração do .env.example, a mesma em qualquer máquina."""
    return make_settings()


@pytest.fixture
def db_client(
    db_session: Session, clock: FrozenClock, outbox: Outbox, settings: Settings
) -> Iterator[TestClient]:
    """Cliente HTTP da API usando a sessão do banco de testes, o relógio `clock`, a
    caixa de saída `outbox`, que captura os e-mails em vez de enviá-los, e a
    configuração `settings`."""
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_settings, None)
