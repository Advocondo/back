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
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.users import DEFAULT_PASSWORD, CreateUser
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


NEW_PASSWORD = "nova-senha-segura"  # gitleaks:allow (test-only password)


def update_profile(
    client: TestClient, headers: dict[str, str], payload: dict[str, Any]
) -> httpx.Response:
    response: httpx.Response = client.patch("/users/me", json=payload, headers=headers)
    return response


def log_in(client: TestClient, email: str, password: str) -> int:
    response: httpx.Response = client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    return response.status_code


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


class TestEditProfile:
    def test_name_is_changed_without_the_current_password(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US05-CA01"""
        headers = authenticate_as(create_user(name="Ana Souza"))

        response = update_profile(db_client, headers, {"name": "  Ana Lima  "})

        assert response.status_code == 200
        assert response.json()["name"] == "Ana Lima"
        assert db_client.get("/auth/me", headers=headers).json()["name"] == "Ana Lima"

    def test_email_is_changed_with_the_current_password(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US05-CA01"""
        headers = authenticate_as(create_user(email="ana@example.com"))

        response = update_profile(
            db_client,
            headers,
            {"email": " Ana.Lima@Example.com ", "current_password": DEFAULT_PASSWORD},
        )

        assert response.status_code == 200
        assert response.json()["email"] == "ana.lima@example.com"
        assert log_in(db_client, "ana.lima@example.com", DEFAULT_PASSWORD) == 200
        assert log_in(db_client, "ana@example.com", DEFAULT_PASSWORD) == 401

    def test_password_is_changed_with_the_current_password(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US05-CA01"""
        headers = authenticate_as(create_user(email="ana@example.com"))

        response = update_profile(
            db_client,
            headers,
            {"new_password": NEW_PASSWORD, "current_password": DEFAULT_PASSWORD},
        )

        assert response.status_code == 200
        assert log_in(db_client, "ana@example.com", NEW_PASSWORD) == 200
        assert log_in(db_client, "ana@example.com", DEFAULT_PASSWORD) == 401

    @pytest.mark.parametrize(
        "change",
        [
            pytest.param({"email": "ana.lima@example.com"}, id="email"),
            pytest.param({"new_password": NEW_PASSWORD}, id="password"),
        ],
    )
    def test_email_or_password_change_requires_the_current_password(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        change: dict[str, str],
    ) -> None:
        """US05-CA02"""
        headers = authenticate_as(create_user(email="ana@example.com"))

        response = update_profile(db_client, headers, change)

        assert response.status_code == 422
        assert response.json() == {
            "detail": "Informe a senha atual para alterar o e-mail ou a senha."
        }
        assert log_in(db_client, "ana@example.com", DEFAULT_PASSWORD) == 200

    @pytest.mark.parametrize(
        "change",
        [
            pytest.param({"email": "ana.lima@example.com"}, id="email"),
            pytest.param({"new_password": NEW_PASSWORD}, id="password"),
        ],
    )
    def test_email_or_password_change_with_a_wrong_current_password_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        change: dict[str, str],
    ) -> None:
        """US05-CA02"""
        headers = authenticate_as(create_user(email="ana@example.com"))

        response = update_profile(
            db_client, headers, change | {"current_password": "senha-errada"}
        )

        assert response.status_code == 422
        assert response.json() == {"detail": "A senha atual está incorreta."}
        assert log_in(db_client, "ana@example.com", DEFAULT_PASSWORD) == 200

    def test_same_email_in_another_case_does_not_require_the_current_password(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers = authenticate_as(create_user(email="ana@example.com"))

        response = update_profile(
            db_client, headers, {"name": "Ana Lima", "email": "ANA@example.com"}
        )

        assert response.status_code == 200
        assert response.json()["email"] == "ana@example.com"

    def test_email_of_another_user_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers = authenticate_as(create_user(email="ana@example.com"))
        create_user(email="bruno@example.com")

        response = update_profile(
            db_client,
            headers,
            {"email": "bruno@example.com", "current_password": DEFAULT_PASSWORD},
        )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "Este e-mail já está em uso por outro usuário."
        }

    def test_wrong_current_password_is_checked_before_the_email_is_looked_up(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers = authenticate_as(create_user(email="ana@example.com"))
        create_user(email="bruno@example.com")

        response = update_profile(
            db_client,
            headers,
            {"email": "bruno@example.com", "current_password": "senha-errada"},
        )

        assert response.status_code == 422
        assert response.json() == {"detail": "A senha atual está incorreta."}

    def test_password_change_ends_the_sessions_on_other_devices(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        user = create_user()
        this_device = authenticate_as(user)
        other_device = authenticate_as(user)

        update_profile(
            db_client,
            this_device,
            {"new_password": NEW_PASSWORD, "current_password": DEFAULT_PASSWORD},
        )

        assert db_client.get("/auth/me", headers=this_device).status_code == 200
        assert db_client.get("/auth/me", headers=other_device).status_code == 401

    def test_name_change_keeps_the_sessions_on_other_devices(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        user = create_user()
        this_device = authenticate_as(user)
        other_device = authenticate_as(user)

        update_profile(db_client, this_device, {"name": "Ana Lima"})

        assert db_client.get("/auth/me", headers=other_device).status_code == 200

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({}, id="nothing-to-change"),
            pytest.param({"current_password": DEFAULT_PASSWORD}, id="only-password"),
            pytest.param({"name": "   "}, id="blank-name"),
            pytest.param({"email": "ana-sem-arroba"}, id="bad-email"),
            pytest.param(
                {"new_password": "a" * (MAX_PASSWORD_LENGTH + 1)},
                id="password-too-long",
            ),
        ],
    )
    def test_invalid_request_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        payload: dict[str, str],
    ) -> None:
        headers = authenticate_as(create_user())

        response = update_profile(db_client, headers, payload)

        assert response.status_code == 422

    def test_new_password_must_have_the_minimum_length(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers = authenticate_as(create_user())

        response = update_profile(
            db_client,
            headers,
            {"new_password": "curta", "current_password": DEFAULT_PASSWORD},
        )

        assert response.status_code == 422
        assert response.json() == {
            "detail": "A senha precisa ter pelo menos 8 caracteres."
        }

    @pytest.mark.parametrize(
        "role",
        [
            pytest.param(Role.OPERATOR, id="operator"),
            pytest.param(Role.CLIENT, id="client"),
        ],
    )
    def test_user_cannot_make_themselves_an_administrator(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        role: Role,
    ) -> None:
        user = create_user(role=role)
        headers = authenticate_as(user)

        response = update_profile(
            db_client,
            headers,
            {"name": "Ana Lima", "role": "admin", "current_password": DEFAULT_PASSWORD},
        )

        db_session.refresh(user)
        assert response.status_code == 422
        assert (user.role, user.name) == (role, "Ana Souza")

    @pytest.mark.parametrize(
        "field",
        [
            pytest.param({"role": "client"}, id="role"),
            pytest.param({"status": "inactive"}, id="status"),
            pytest.param({"id": "00000000-0000-0000-0000-000000000000"}, id="id"),
            pytest.param({"password_hash": "hash"}, id="password-hash"),
        ],
    )
    def test_fields_outside_the_profile_are_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        field: dict[str, str],
    ) -> None:
        headers = authenticate_as(create_user(role=Role.ADMIN))

        response = update_profile(db_client, headers, {"name": "Ana Lima"} | field)

        assert response.status_code == 422
        assert db_client.get("/auth/me", headers=headers).json()["name"] == "Ana Souza"

    def test_editing_the_profile_requires_a_valid_session(
        self, db_client: TestClient
    ) -> None:
        response = db_client.patch("/users/me", json={"name": "Ana Lima"})

        assert response.status_code == 401
