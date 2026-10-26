from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import Engine, String, create_engine, func, inspect, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

import advocondo.models  # noqa: F401
from advocondo.db import Base
from advocondo.landing.schemas import LandingContent
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

    def test_upgrade_writes_a_valid_initial_landing_page(
        self, alembic_config: Config, migrations_engine: Engine
    ) -> None:
        """US04: the site is complete right after the deploy, before any edit."""
        command.upgrade(alembic_config, "head")

        with migrations_engine.connect() as connection:
            rows = connection.execute(text("SELECT key, content FROM landing_blocks"))
            content = LandingContent.model_validate({key: value for key, value in rows})

        assert content.team.members

    def test_initial_landing_page_has_no_placeholder_reviews(
        self, alembic_config: Config, migrations_engine: Engine
    ) -> None:
        """The prototype's reviews are paraphrased; only real reviews may be published."""
        command.upgrade(alembic_config, "head")

        with migrations_engine.connect() as connection:
            reviews = connection.scalar(
                text(
                    "SELECT content -> 'reviews' FROM landing_blocks WHERE key = 'reviews'"
                )
            )

        assert reviews == []

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

    def test_upgrade_moves_the_monthly_goal_to_the_goals_table(
        self, alembic_config: Config, migrations_engine: Engine
    ) -> None:
        """R1: a meta gravada no usuário vira a meta do mês atual da US36, sem
        sobrescrever uma meta que já existe nem criar meta para outros perfis."""
        command.upgrade(alembic_config, "ee9f5a69e771")
        with migrations_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (email, name, role, status, password_hash,"
                    " monthly_goal) VALUES"
                    " ('ana@example.com', 'Ana', 'operator', 'active', 'x', 300),"
                    " ('bruno@example.com', 'Bruno', 'operator', 'active', 'x', 0),"
                    " ('carla@example.com', 'Carla', 'operator', 'active', 'x', 200),"
                    " ('sindico@example.com', 'Síndico', 'client', 'active', 'x', 50)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO goals (user_id, year, month, target_amount)"
                    " SELECT id,"
                    " EXTRACT(YEAR FROM now() AT TIME ZONE 'America/Sao_Paulo'),"
                    " EXTRACT(MONTH FROM now() AT TIME ZONE 'America/Sao_Paulo'),"
                    " 900 FROM users WHERE email = 'carla@example.com'"
                )
            )

        command.upgrade(alembic_config, "71e2626a3918")

        with migrations_engine.connect() as connection:
            goals: dict[str, int] = dict(
                connection.execute(
                    text(
                        "SELECT users.name, goals.target_amount FROM goals"
                        " JOIN users ON users.id = goals.user_id"
                        " WHERE (goals.year, goals.month) = ("
                        " EXTRACT(YEAR FROM now() AT TIME ZONE 'America/Sao_Paulo'),"
                        " EXTRACT(MONTH FROM now() AT TIME ZONE 'America/Sao_Paulo'))"
                    )
                ).all()
            )
        columns = {
            column["name"] for column in inspect(migrations_engine).get_columns("users")
        }

        assert goals == {"Ana": 300, "Carla": 900}
        assert "monthly_goal" not in columns
