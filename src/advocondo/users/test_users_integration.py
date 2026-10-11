from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from advocondo.common.passwords import MAX_PASSWORD_LENGTH
from advocondo.config import Settings, get_settings
from advocondo.main import app
from advocondo.users.models import Role, User, UserStatus
from tests.fixtures.users import CreateUser
from tests.support.settings import make_settings

PASSWORD = "senha-do-admin"
SETUP_TOKEN = "token-de-configuracao-usado-so-nos-testes"  # gitleaks:allow
FIRST_ADMIN = {"email": "Ana@Example.com", "name": "Ana Souza", "password": PASSWORD}


def set_up(
    client: TestClient,
    payload: dict[str, str] = FIRST_ADMIN,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    response: httpx.Response = client.post(
        "/setup", json=payload, headers=headers or {"X-Setup-Token": SETUP_TOKEN}
    )
    return response


def count_users(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(User)) or 0


def build_user(**overrides: Any) -> User:
    fields: dict[str, Any] = {
        "email": "ana@example.com",
        "name": "Ana Souza",
        "role": Role.OPERATOR,
        "status": UserStatus.ACTIVE,
        "password_hash": "hash",
    }
    return User(**(fields | overrides))


class TestFirstAdminSetup:
    @pytest.fixture
    def settings(self) -> Settings:
        return make_settings(setup_token=SETUP_TOKEN)

    def test_first_admin_is_created_and_can_log_in(self, db_client: TestClient) -> None:
        response = set_up(db_client)

        login = db_client.post(
            "/auth/login", json={"email": "ana@example.com", "password": PASSWORD}
        )
        assert response.status_code == 201
        assert response.json()["email"] == "ana@example.com"
        assert login.status_code == 200
        assert login.json()["user"]["role"] == Role.ADMIN.value

    def test_first_admin_is_stored_as_active_administrator(
        self, db_client: TestClient, db_session: Session
    ) -> None:
        set_up(db_client)

        user = db_session.scalars(select(User)).one()
        assert (user.email, user.name, user.role, user.status) == (
            "ana@example.com",
            "Ana Souza",
            Role.ADMIN,
            UserStatus.ACTIVE,
        )

    def test_admin_is_not_created_when_a_user_already_exists(
        self, db_client: TestClient, db_session: Session, create_user: CreateUser
    ) -> None:
        create_user(email="existente@example.com")

        response = set_up(db_client)

        assert response.status_code == 422
        assert response.json() == {
            "detail": "O primeiro usuário já foi criado. Os demais entram por convite."
        }
        assert count_users(db_session) == 1

    @pytest.mark.parametrize(
        "headers",
        [
            pytest.param({}, id="no-token"),
            pytest.param({"X-Setup-Token": "outro-token"}, id="wrong-token"),
        ],
    )
    def test_admin_is_not_created_without_the_setup_token(
        self, db_client: TestClient, db_session: Session, headers: dict[str, str]
    ) -> None:
        response = db_client.post("/setup", json=FIRST_ADMIN, headers=headers)

        assert response.status_code == 403
        assert response.json() == {"detail": "Token de configuração inválido."}
        assert count_users(db_session) == 0

    def test_token_is_checked_before_revealing_that_users_exist(
        self, db_client: TestClient, create_user: CreateUser
    ) -> None:
        create_user(email="existente@example.com")

        response = db_client.post("/setup", json=FIRST_ADMIN)

        assert response.status_code == 403
        assert response.json() == {"detail": "Token de configuração inválido."}

    def test_token_is_checked_before_validating_the_request_body(
        self, db_client: TestClient
    ) -> None:
        response = db_client.post("/setup", json={"email": "ana-sem-arroba"})

        assert response.status_code == 403
        assert response.json() == {"detail": "Token de configuração inválido."}

    def test_setup_is_unavailable_when_no_token_is_configured(
        self, db_client: TestClient, db_session: Session
    ) -> None:
        app.dependency_overrides[get_settings] = lambda: make_settings(setup_token="")

        response = set_up(db_client)

        assert response.status_code == 404
        assert count_users(db_session) == 0

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param(FIRST_ADMIN | {"email": "ana-sem-arroba"}, id="bad-email"),
            pytest.param(FIRST_ADMIN | {"name": "   "}, id="blank-name"),
            pytest.param(FIRST_ADMIN | {"password": "curta"}, id="password-too-short"),
            pytest.param(
                FIRST_ADMIN | {"password": "a" * (MAX_PASSWORD_LENGTH + 1)},
                id="password-too-long",
            ),
        ],
    )
    def test_admin_is_not_created_with_invalid_input(
        self, db_client: TestClient, db_session: Session, payload: dict[str, str]
    ) -> None:
        response = set_up(db_client, payload)

        assert response.status_code == 422
        assert count_users(db_session) == 0


class TestUserModel:
    def test_new_user_starts_pending_with_generated_id_and_timestamps(
        self,
        db_session: Session,
    ) -> None:
        user = User(email="ana@example.com", name="Ana Souza", role=Role.OPERATOR)

        db_session.add(user)
        db_session.flush()

        assert user.status == UserStatus.PENDING
        assert user.id is not None
        assert user.created_at is not None
        assert user.updated_at is not None

    def test_email_is_unique(self, db_session: Session) -> None:
        db_session.add(build_user(email="ana@example.com"))
        db_session.flush()

        db_session.add(build_user(email="ana@example.com", name="Outra Ana"))

        with pytest.raises(IntegrityError, match="uq_users_email"):
            db_session.flush()

    def test_email_must_be_stored_lowercase(self, db_session: Session) -> None:
        db_session.add(build_user(email="Ana@Example.com"))

        with pytest.raises(IntegrityError, match="ck_users_email_is_lowercase"):
            db_session.flush()

    def test_active_user_must_have_a_password(self, db_session: Session) -> None:
        db_session.add(build_user(status=UserStatus.ACTIVE, password_hash=None))

        with pytest.raises(IntegrityError, match="ck_users_active_user_has_password"):
            db_session.flush()

    @pytest.mark.parametrize(
        "status",
        [
            pytest.param(UserStatus.PENDING, id="pending-invite"),
            pytest.param(UserStatus.INACTIVE, id="inactive"),
        ],
    )
    def test_user_that_is_not_active_may_have_no_password(
        self, db_session: Session, status: UserStatus
    ) -> None:
        db_session.add(build_user(status=status, password_hash=None))
        db_session.flush()

        assert db_session.scalar(select(User.status)) == status
