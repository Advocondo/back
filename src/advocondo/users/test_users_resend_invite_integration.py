import re
import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from advocondo.common.email import EmailMessage, get_email_sender
from advocondo.main import app
from advocondo.users.models import (
    AuditAction,
    Role,
    User,
    UserAuditLog,
    UserInvite,
    UserStatus,
)
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.users import CreateUser
from tests.support.email import Outbox

PASSWORD = "senha-do-convite-123"  # gitleaks:allow (test-only password)


class BrokenEmailSender:
    def send(self, message: EmailMessage) -> None:
        raise ConnectionError("SMTP fora do ar")


@pytest.fixture
def broken_email(db_client: TestClient) -> Iterator[None]:
    """Depende de db_client, que também mexe nas dependências da aplicação."""
    app.dependency_overrides[get_email_sender] = BrokenEmailSender
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_email_sender, None)


@pytest.fixture
def admin(create_user: CreateUser) -> User:
    return create_user(email="adm@example.com", role=Role.ADMIN)


@pytest.fixture
def admin_headers(admin: User, authenticate_as: AuthenticateAs) -> dict[str, str]:
    return authenticate_as(admin)


def invite(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    response = client.post(
        "/users/invites",
        json={"email": "novo@example.com", "name": "Novo", "role": "operator"},
        headers=headers,
    )
    assert response.status_code == 201
    body: dict[str, object] = response.json()
    return body


def token_in(message: EmailMessage) -> str:
    match = re.search(r"[?&]token=([A-Za-z0-9_\-]+)", message.body)
    assert match is not None
    return match.group(1)


def accept(client: TestClient, token: str) -> int:
    status_code: int = client.post(
        "/users/invites/accept", json={"token": token, "password": PASSWORD}
    ).status_code
    return status_code


class TestInviteSent:
    def test_says_the_email_went_out(
        self, db_client: TestClient, admin_headers: dict[str, str], outbox: Outbox
    ) -> None:
        assert invite(db_client, admin_headers)["invite_sent"] is True

    @pytest.mark.usefixtures("broken_email")
    def test_says_when_the_email_failed_and_keeps_the_user(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        body = invite(db_client, admin_headers)

        assert body["invite_sent"] is False
        assert body["status"] == "pending"


class TestResendInvite:
    def test_sends_a_new_link_and_the_old_one_stops_working(
        self, db_client: TestClient, admin_headers: dict[str, str], outbox: Outbox
    ) -> None:
        user_id = invite(db_client, admin_headers)["id"]
        old_token = token_in(outbox.messages[-1])

        response = db_client.post(
            f"/users/{user_id}/invite/resend", headers=admin_headers
        )

        assert response.status_code == 200
        assert response.json()["invite_sent"] is True
        assert len(outbox.messages) == 2
        new_token = token_in(outbox.messages[-1])
        assert new_token != old_token
        assert accept(db_client, old_token) == 422
        assert accept(db_client, new_token) == 200

    def test_renews_an_expired_invite(
        self,
        db_client: TestClient,
        db_session: Session,
        admin_headers: dict[str, str],
        outbox: Outbox,
    ) -> None:
        user_id = invite(db_client, admin_headers)["id"]
        stored = db_session.scalar(select(UserInvite))
        assert stored is not None
        stored.expires_at -= timedelta(days=30)
        db_session.flush()
        assert accept(db_client, token_in(outbox.messages[-1])) == 422

        db_client.post(f"/users/{user_id}/invite/resend", headers=admin_headers)

        assert accept(db_client, token_in(outbox.messages[-1])) == 200

    def test_creates_the_invite_when_the_row_is_missing(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        admin_headers: dict[str, str],
        outbox: Outbox,
    ) -> None:
        pending = create_user(
            email="sem@example.com", status=UserStatus.PENDING, password=None
        )

        response = db_client.post(
            f"/users/{pending.id}/invite/resend", headers=admin_headers
        )

        assert response.status_code == 200
        assert accept(db_client, token_in(outbox.messages[-1])) == 200

    def test_records_who_resent_in_the_history(
        self,
        db_client: TestClient,
        db_session: Session,
        admin: User,
        admin_headers: dict[str, str],
        outbox: Outbox,
    ) -> None:
        user_id = invite(db_client, admin_headers)["id"]

        db_client.post(f"/users/{user_id}/invite/resend", headers=admin_headers)

        logs = db_session.scalars(
            select(UserAuditLog).where(UserAuditLog.action == AuditAction.INVITED)
        ).all()
        assert len(logs) == 2
        assert {log.actor_id for log in logs} == {admin.id}

    @pytest.mark.usefixtures("broken_email")
    def test_says_when_the_email_failed(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        admin_headers: dict[str, str],
    ) -> None:
        pending = create_user(
            email="sem@example.com", status=UserStatus.PENDING, password=None
        )

        response = db_client.post(
            f"/users/{pending.id}/invite/resend", headers=admin_headers
        )

        assert response.status_code == 200
        assert response.json()["invite_sent"] is False

    def test_refuses_who_already_accepted(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        admin_headers: dict[str, str],
    ) -> None:
        active = create_user(email="ativo@example.com")

        response = db_client.post(
            f"/users/{active.id}/invite/resend", headers=admin_headers
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "Este usuário já aceitou o convite."

    def test_unknown_user_is_not_found(
        self, db_client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        response = db_client.post(
            f"/users/{uuid.uuid4()}/invite/resend", headers=admin_headers
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "role",
        [
            pytest.param(Role.OPERATOR, id="operator"),
            pytest.param(Role.CLIENT, id="client"),
        ],
    )
    def test_only_the_administrator_resends(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        role: Role,
    ) -> None:
        headers = authenticate_as(create_user(role=role))

        response = db_client.post(
            f"/users/{uuid.uuid4()}/invite/resend", headers=headers
        )

        assert response.status_code == 403
