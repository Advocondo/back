from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from advocondo.config import Settings
from advocondo.users.models import Role, UserStatus
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.users import DEFAULT_PASSWORD, CreateUser
from tests.support.clock import DEFAULT_NOW, FrozenClock

GENERIC_ERROR = {"detail": "E-mail ou senha inválidos."}


def log_in(
    client: TestClient, email: str, password: str, *, remember_me: bool = False
) -> httpx.Response:
    response: httpx.Response = client.post(
        "/auth/login",
        json={"email": email, "password": password, "remember_me": remember_me},
    )
    return response


EXPIRED_SESSION_ERROR = {"detail": "Sua sessão expirou. Faça login novamente."}


class TestLogin:
    @pytest.mark.parametrize(
        "role",
        [
            pytest.param(Role.ADMIN, id="admin"),
            pytest.param(Role.OPERATOR, id="operator"),
            pytest.param(Role.CLIENT, id="client"),
        ],
    )
    def test_valid_credentials_return_the_user_role_to_choose_the_panel(
        self, db_client: TestClient, create_user: CreateUser, role: Role
    ) -> None:
        """US02-CA01"""
        user = create_user(email="ana@example.com", role=role)

        response = log_in(db_client, "ana@example.com", DEFAULT_PASSWORD)

        assert response.status_code == 200
        assert response.json()["user"] == {
            "id": str(user.id),
            "name": user.name,
            "email": "ana@example.com",
            "role": role.value,
        }

    def test_token_from_login_gives_access_to_the_api(
        self, db_client: TestClient, create_user: CreateUser
    ) -> None:
        """US02-CA01"""
        user = create_user(email="ana@example.com")
        token = log_in(db_client, "ana@example.com", DEFAULT_PASSWORD).json()[
            "access_token"
        ]

        response = db_client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        assert response.json()["id"] == str(user.id)

    def test_email_is_matched_ignoring_case_and_surrounding_spaces(
        self, db_client: TestClient, create_user: CreateUser
    ) -> None:
        """US02-CA01"""
        create_user(email="ana@example.com")

        response = log_in(db_client, "  Ana@Example.COM ", DEFAULT_PASSWORD)

        assert response.status_code == 200

    @pytest.mark.parametrize(
        ("remember_me", "duration_setting"),
        [
            pytest.param(False, "session_duration", id="default-session"),
            pytest.param(True, "remembered_session_duration", id="keep-me-logged-in"),
        ],
    )
    def test_session_lasts_longer_when_the_user_asks_to_stay_logged_in(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        settings: Settings,
        remember_me: bool,
        duration_setting: str,
    ) -> None:
        create_user(email="ana@example.com")

        response = log_in(
            db_client, "ana@example.com", DEFAULT_PASSWORD, remember_me=remember_me
        )

        duration: timedelta = getattr(settings, duration_setting)
        expires_at = response.json()["expires_at"]
        assert expires_at == (DEFAULT_NOW + duration).isoformat().replace("+00:00", "Z")

    @pytest.mark.parametrize(
        ("email", "password"),
        [
            pytest.param("ana@example.com", "senha-errada", id="wrong-password"),
            pytest.param("ninguem@example.com", DEFAULT_PASSWORD, id="unknown-email"),
        ],
    )
    def test_invalid_credentials_get_a_generic_error(
        self, db_client: TestClient, create_user: CreateUser, email: str, password: str
    ) -> None:
        """US02-CA02"""
        create_user(email="ana@example.com")

        response = log_in(db_client, email, password)

        assert response.status_code == 401
        assert response.json() == GENERIC_ERROR

    @pytest.mark.parametrize(
        ("status", "password"),
        [
            pytest.param(UserStatus.INACTIVE, DEFAULT_PASSWORD, id="inactive"),
            pytest.param(UserStatus.PENDING, None, id="pending-invite"),
        ],
    )
    def test_user_that_is_not_active_cannot_log_in(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        status: UserStatus,
        password: str | None,
    ) -> None:
        """US02-CA03"""
        create_user(email="ana@example.com", status=status, password=password)

        response = log_in(db_client, "ana@example.com", DEFAULT_PASSWORD)

        assert response.status_code == 401
        assert response.json() == GENERIC_ERROR


class TestCurrentUser:
    def test_logged_in_user_gets_their_own_data(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        user = create_user(email="ana@example.com", name="Ana Souza", role=Role.ADMIN)

        response = db_client.get("/auth/me", headers=authenticate_as(user))

        assert response.status_code == 200
        assert response.json() == {
            "id": str(user.id),
            "name": "Ana Souza",
            "email": "ana@example.com",
            "role": "admin",
        }

    @pytest.mark.parametrize(
        "headers",
        [
            pytest.param({}, id="no-token"),
            pytest.param({"Authorization": "Bearer unknown-token"}, id="unknown-token"),
        ],
    )
    def test_request_without_a_valid_token_is_refused(
        self, db_client: TestClient, headers: dict[str, str]
    ) -> None:
        response = db_client.get("/auth/me", headers=headers)

        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"

    def test_expired_session_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        clock: FrozenClock,
        settings: Settings,
    ) -> None:
        headers = authenticate_as(create_user())
        clock.advance(settings.session_duration)

        response = db_client.get("/auth/me", headers=headers)

        assert response.status_code == 401
        assert response.json() == EXPIRED_SESSION_ERROR

    def test_user_inactivated_after_logging_in_loses_access(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US02-CA03"""
        user = create_user()
        headers = authenticate_as(user)
        user.status = UserStatus.INACTIVE
        db_session.flush()

        response = db_client.get("/auth/me", headers=headers)

        assert response.status_code == 401
