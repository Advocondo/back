from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from advocondo.users.models import Role, UserStatus
from tests.fixtures.users import DEFAULT_PASSWORD, CreateUser
from tests.support.clock import DEFAULT_NOW

GENERIC_ERROR = {"detail": "E-mail ou senha inválidos."}


def log_in(
    client: TestClient, email: str, password: str, *, remember_me: bool = False
) -> httpx.Response:
    response: httpx.Response = client.post(
        "/auth/login",
        json={"email": email, "password": password, "remember_me": remember_me},
    )
    return response


@pytest.mark.parametrize(
    "role",
    [
        pytest.param(Role.ADMIN, id="admin"),
        pytest.param(Role.OPERATOR, id="operator"),
        pytest.param(Role.CLIENT, id="client"),
    ],
)
def test_valid_credentials_return_the_user_role_to_choose_the_panel(
    db_client: TestClient, create_user: CreateUser, role: Role
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
    db_client: TestClient, create_user: CreateUser
) -> None:
    """US02-CA01"""
    user = create_user(email="ana@example.com")
    token = log_in(db_client, "ana@example.com", DEFAULT_PASSWORD).json()[
        "access_token"
    ]

    response = db_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)


def test_email_is_matched_ignoring_case_and_surrounding_spaces(
    db_client: TestClient, create_user: CreateUser
) -> None:
    """US02-CA01"""
    create_user(email="ana@example.com")

    response = log_in(db_client, "  Ana@Example.COM ", DEFAULT_PASSWORD)

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("remember_me", "duration"),
    [
        pytest.param(False, timedelta(hours=12), id="default-session"),
        pytest.param(True, timedelta(days=30), id="keep-me-logged-in"),
    ],
)
def test_session_lasts_longer_when_the_user_asks_to_stay_logged_in(
    db_client: TestClient,
    create_user: CreateUser,
    remember_me: bool,
    duration: timedelta,
) -> None:
    create_user(email="ana@example.com")

    response = log_in(
        db_client, "ana@example.com", DEFAULT_PASSWORD, remember_me=remember_me
    )

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
    db_client: TestClient, create_user: CreateUser, email: str, password: str
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
