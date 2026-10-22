from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import Engine, String, create_engine, func, inspect, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

import advocondo.models  # noqa: F401
from advocondo.db import Base
from tests.support.database import ensure_database_exists, get_test_database_url


class RascunhoBase(DeclarativeBase):
    """Fora do Base da aplicação: não é modelo do domínio e não tem migration."""


class Rascunho(RascunhoBase):
    """Tabela usada só nos testes, até existirem os modelos do domínio (#42)."""

    __tablename__ = "rascunho_teste"

    id: Mapped[int] = mapped_column(primary_key=True)
    texto: Mapped[str] = mapped_column(String(100))


PROJECT_ROOT = Path(__file__).resolve().parents[2]


pytestmark = pytest.mark.integration


class TestHealthReady:
    def test_readiness_verifica_o_banco(self, db_client: TestClient) -> None:
        response = db_client.get("/health/ready")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "checks": {"database": "ok"}}


class TestIsolation:
    @pytest.fixture(scope="module", autouse=True)
    def tabela_rascunho(self, db_engine: Engine) -> Iterator[None]:
        RascunhoBase.metadata.create_all(db_engine)
        yield
        RascunhoBase.metadata.drop_all(db_engine)

    @pytest.mark.parametrize("texto", ["primeiro", "segundo", "terceiro"])
    def test_cada_teste_comeca_com_banco_limpo(
        self, db_session: Session, texto: str
    ) -> None:
        db_session.add(Rascunho(texto=texto))
        db_session.commit()

        assert db_session.scalar(select(func.count()).select_from(Rascunho)) == 1
        assert db_session.scalar(select(Rascunho.texto)) == texto


class TestMigrations:
    @pytest.fixture(scope="module")
    def migrations_url(self) -> URL:
        # A database of its own: the suite's test database is built from the models.
        url = get_test_database_url().set(database="advocondo_migrations_test")
        ensure_database_exists(url)
        return url

    @pytest.fixture(scope="module")
    def migrations_engine(self, migrations_url: URL) -> Iterator[Engine]:
        engine = create_engine(migrations_url)
        yield engine
        engine.dispose()

    @pytest.fixture
    def alembic_config(self, migrations_url: URL) -> Iterator[Config]:
        config = Config(PROJECT_ROOT / "alembic.ini")
        config.set_main_option(
            "sqlalchemy.url", migrations_url.render_as_string(hide_password=False)
        )
        command.downgrade(config, "base")
        yield config
        command.downgrade(config, "base")

    def test_upgrade_builds_the_schema_described_by_the_models(
        self, alembic_config: Config, migrations_engine: Engine
    ) -> None:
        command.upgrade(alembic_config, "head")

        with migrations_engine.connect() as connection:
            differences = compare_metadata(
                MigrationContext.configure(connection), Base.metadata
            )

        assert differences == []

    def test_downgrade_removes_every_table(
        self, alembic_config: Config, migrations_engine: Engine
    ) -> None:
        command.upgrade(alembic_config, "head")

        command.downgrade(alembic_config, "base")

        assert inspect(migrations_engine).get_table_names() == ["alembic_version"]

    def test_upgrade_lets_an_agreement_be_cancelled(
        self, alembic_config: Config, migrations_engine: Engine
    ) -> None:
        """O `compare_metadata` não compara CHECK, então a ampliação do status
        precisa ser conferida à parte."""
        command.upgrade(alembic_config, "head")

        inspector = inspect(migrations_engine)
        status_checks = [
            check["sqltext"]
            for check in inspector.get_check_constraints("agreements")
            if check["name"] == "ck_agreements_agreement_status"
        ]
        columns = {column["name"] for column in inspector.get_columns("agreements")}

        assert len(status_checks) == 1
        assert "'cancelled'" in status_checks[0]
        assert {"cancelled_at", "cancellation_reason"} <= columns
