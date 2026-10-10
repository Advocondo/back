from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from advocondo.users.models import Role, UserStatus
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.users import CreateUser
from tests.support.clock import FrozenClock

EXPIRED_SESSION_ERROR = {"detail": "Sua sessão expirou. Faça login novamente."}


def test_logged_in_user_gets_their_own_data(
    db_client: TestClient, create_user: CreateUser, authenticate_as: AuthenticateAs
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
    db_client: TestClient, headers: dict[str, str]
) -> None:
    response = db_client.get("/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_expired_session_is_refused(
    db_client: TestClient,
    create_user: CreateUser,
    authenticate_as: AuthenticateAs,
    clock: FrozenClock,
) -> None:
    headers = authenticate_as(create_user())
    clock.advance(timedelta(hours=12))

    response = db_client.get("/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.json() == EXPIRED_SESSION_ERROR


def test_user_inactivated_after_logging_in_loses_access(
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
