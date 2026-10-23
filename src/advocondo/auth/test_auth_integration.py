import re
import runpy
import sys
from contextlib import nullcontext
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import advocondo.common.clock
import advocondo.db
from advocondo.auth.cleanup import delete_expired
from advocondo.auth.models import PasswordResetLink, UserSession
from advocondo.common.email import EmailMessage, get_email_sender
from advocondo.common.tokens import generate_opaque_token, hash_token
from advocondo.config import Settings
from advocondo.main import app
from advocondo.users.models import Role, User, UserStatus
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.users import DEFAULT_PASSWORD, CreateUser
from tests.support.clock import DEFAULT_NOW, FrozenClock
from tests.support.email import Outbox

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


NEW_PASSWORD = "nova-senha-segura"


REQUEST_ANSWER = {
    "detail": "Se o e-mail estiver cadastrado, você receberá um link para redefinir a senha."
}


INVALID_LINK_ERROR = {
    "detail": "Este link de redefinição é inválido ou expirou. Solicite um novo."
}


LINK_PATTERN = re.compile(r"https?://\S+")


def request_reset(client: TestClient, email: str) -> httpx.Response:
    response: httpx.Response = client.post(
        "/auth/password-reset", json={"email": email}
    )
    return response


def reset_password(
    client: TestClient, token: str, new_password: str = NEW_PASSWORD
) -> httpx.Response:
    response: httpx.Response = client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "new_password": new_password},
    )
    return response


def log_in_with_password(client: TestClient, password: str) -> httpx.Response:
    response: httpx.Response = client.post(
        "/auth/login", json={"email": "ana@example.com", "password": password}
    )
    return response


def link_in(outbox: Outbox) -> str:
    match = LINK_PATTERN.search(outbox.messages[-1].body)
    assert match is not None
    return match.group()


def token_in(outbox: Outbox) -> str:
    return parse_qs(urlparse(link_in(outbox)).query)["token"][0]


def add_reset_link(db_session: Session, user: User, *, expired_ago: timedelta) -> None:
    """A link as a request leaves it, created a link duration before it expired."""
    expires_at = DEFAULT_NOW - expired_ago
    db_session.add(
        PasswordResetLink(
            user=user,
            token_hash=hash_token(generate_opaque_token()),
            created_at=expires_at - timedelta(minutes=60),
            expires_at=expires_at,
        )
    )
    db_session.flush()


def count_sessions(db_session: Session) -> int:
    return db_session.scalar(select(func.count()).select_from(UserSession)) or 0


def count_reset_links(db_session: Session) -> int:
    return db_session.scalar(select(func.count()).select_from(PasswordResetLink)) or 0


class BrokenEmailSender:
    def send(self, message: EmailMessage) -> None:
        raise ConnectionError("SMTP fora do ar")


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


class TestPasswordReset:
    def test_registered_user_receives_a_reset_link_to_the_front_end_page(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        outbox: Outbox,
        settings: Settings,
    ) -> None:
        """US03-CA01"""
        create_user(email="ana@example.com")

        response = request_reset(db_client, "Ana@Example.com")

        link = urlparse(link_in(outbox))
        assert response.status_code == 202
        assert response.json() == REQUEST_ANSWER
        assert [message.to for message in outbox.messages] == ["ana@example.com"]
        assert f"{link.scheme}://{link.netloc}" == settings.frontend_url
        assert link.path == "/redefinir-senha"

    def test_email_tells_how_long_the_link_is_valid(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        outbox: Outbox,
        settings: Settings,
    ) -> None:
        """US03-CA01"""
        create_user(email="ana@example.com")

        request_reset(db_client, "ana@example.com")

        minutes = settings.password_reset_link_minutes
        assert f"em até {minutes} minutos" in outbox.messages[-1].body

    def test_link_within_the_time_limit_sets_the_new_password(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        outbox: Outbox,
        clock: FrozenClock,
        settings: Settings,
    ) -> None:
        """US03-CA01"""
        create_user(email="ana@example.com")
        request_reset(db_client, "ana@example.com")
        clock.advance(settings.password_reset_link_duration - timedelta(seconds=1))

        response = reset_password(db_client, token_in(outbox))

        assert response.status_code == 204
        assert log_in_with_password(db_client, NEW_PASSWORD).status_code == 200

    @pytest.mark.parametrize(
        ("status", "password"),
        [
            pytest.param(UserStatus.INACTIVE, DEFAULT_PASSWORD, id="inactive"),
            pytest.param(UserStatus.PENDING, None, id="pending-invite"),
        ],
    )
    def test_user_that_cannot_log_in_gets_the_same_answer_and_no_email(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        outbox: Outbox,
        status: UserStatus,
        password: str | None,
    ) -> None:
        create_user(email="ana@example.com", status=status, password=password)

        response = request_reset(db_client, "ana@example.com")

        assert response.status_code == 202
        assert response.json() == REQUEST_ANSWER
        assert outbox.messages == []

    def test_unknown_email_gets_the_same_answer_and_no_email(
        self, db_client: TestClient, outbox: Outbox
    ) -> None:
        response = request_reset(db_client, "ninguem@example.com")

        assert response.status_code == 202
        assert response.json() == REQUEST_ANSWER
        assert outbox.messages == []

    def test_expired_link_does_not_reset_the_password(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        outbox: Outbox,
        clock: FrozenClock,
        settings: Settings,
    ) -> None:
        """US03-CA02"""
        create_user(email="ana@example.com")
        request_reset(db_client, "ana@example.com")
        clock.advance(settings.password_reset_link_duration)

        response = reset_password(db_client, token_in(outbox))

        assert response.status_code == 422
        assert response.json() == INVALID_LINK_ERROR
        assert log_in_with_password(db_client, DEFAULT_PASSWORD).status_code == 200

    def test_link_works_only_once(
        self, db_client: TestClient, create_user: CreateUser, outbox: Outbox
    ) -> None:
        """US03-CA02"""
        create_user(email="ana@example.com")
        request_reset(db_client, "ana@example.com")
        token = token_in(outbox)
        reset_password(db_client, token)

        response = reset_password(db_client, token, new_password="outra-senha-qualquer")

        assert response.status_code == 422
        assert response.json() == INVALID_LINK_ERROR

    def test_new_request_invalidates_the_previous_link(
        self, db_client: TestClient, create_user: CreateUser, outbox: Outbox
    ) -> None:
        """US03-CA02"""
        create_user(email="ana@example.com")
        request_reset(db_client, "ana@example.com")
        first_token = token_in(outbox)
        request_reset(db_client, "ana@example.com")

        response = reset_password(db_client, first_token)

        assert response.status_code == 422
        assert response.json() == INVALID_LINK_ERROR

    def test_unknown_token_is_refused(self, db_client: TestClient) -> None:
        """US03-CA02"""
        response = reset_password(db_client, "token-que-nao-existe")

        assert response.status_code == 422
        assert response.json() == INVALID_LINK_ERROR

    def test_user_inactivated_after_requesting_cannot_use_the_link(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        outbox: Outbox,
    ) -> None:
        user = create_user(email="ana@example.com")
        request_reset(db_client, "ana@example.com")
        user.status = UserStatus.INACTIVE
        db_session.flush()

        response = reset_password(db_client, token_in(outbox))

        assert response.status_code == 422
        assert response.json() == INVALID_LINK_ERROR

    def test_new_password_must_have_the_minimum_length(
        self, db_client: TestClient, create_user: CreateUser, outbox: Outbox
    ) -> None:
        create_user(email="ana@example.com")
        request_reset(db_client, "ana@example.com")

        response = reset_password(db_client, token_in(outbox), new_password="curta")

        assert response.status_code == 422
        assert response.json() == {
            "detail": "A senha precisa ter pelo menos 8 caracteres."
        }

    def test_sessions_opened_before_the_reset_stop_working(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        outbox: Outbox,
    ) -> None:
        """US03-CA03"""
        user = create_user(email="ana@example.com")
        old_session_headers = authenticate_as(user)
        request_reset(db_client, "ana@example.com")
        reset_password(db_client, token_in(outbox))

        response = db_client.get("/auth/me", headers=old_session_headers)

        assert response.status_code == 401

    def test_old_password_stops_working_after_the_reset(
        self, db_client: TestClient, create_user: CreateUser, outbox: Outbox
    ) -> None:
        """US03-CA03"""
        create_user(email="ana@example.com")
        request_reset(db_client, "ana@example.com")
        reset_password(db_client, token_in(outbox))

        response = log_in_with_password(db_client, DEFAULT_PASSWORD)

        assert response.status_code == 401

    def test_email_delivery_failure_does_not_change_the_answer(
        self, db_client: TestClient, create_user: CreateUser
    ) -> None:
        create_user(email="ana@example.com")
        app.dependency_overrides[get_email_sender] = BrokenEmailSender

        response = request_reset(db_client, "ana@example.com")

        assert response.status_code == 202
        assert response.json() == REQUEST_ANSWER

    def test_requests_beyond_the_limit_get_the_same_answer_and_no_email(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        outbox: Outbox,
        settings: Settings,
    ) -> None:
        create_user(email="ana@example.com")
        for _ in range(settings.password_reset_max_requests):
            request_reset(db_client, "ana@example.com")

        response = request_reset(db_client, "ana@example.com")

        assert response.status_code == 202
        assert response.json() == REQUEST_ANSWER
        assert len(outbox.messages) == settings.password_reset_max_requests

    def test_requests_are_accepted_again_once_the_window_passes(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        outbox: Outbox,
        clock: FrozenClock,
        settings: Settings,
    ) -> None:
        create_user(email="ana@example.com")
        for _ in range(settings.password_reset_max_requests):
            request_reset(db_client, "ana@example.com")
        clock.advance(settings.password_reset_request_window)

        request_reset(db_client, "ana@example.com")

        assert len(outbox.messages) == settings.password_reset_max_requests + 1

    def test_links_of_the_user_are_deleted_once_the_reset_is_complete(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        outbox: Outbox,
    ) -> None:
        create_user(email="ana@example.com")
        request_reset(db_client, "ana@example.com")
        request_reset(db_client, "ana@example.com")

        reset_password(db_client, token_in(outbox))

        assert (
            db_session.scalar(select(func.count()).select_from(PasswordResetLink)) == 0
        )


class TestLogout:
    def test_logout_ends_the_current_session(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers = authenticate_as(create_user())

        response = db_client.post("/auth/logout", headers=headers)

        assert response.status_code == 204
        assert db_client.get("/auth/me", headers=headers).status_code == 401

    def test_logout_keeps_the_sessions_on_other_devices(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        user = create_user()
        this_device = authenticate_as(user)
        other_device = authenticate_as(user)

        db_client.post("/auth/logout", headers=this_device)

        assert db_client.get("/auth/me", headers=other_device).status_code == 200

    def test_logout_requires_a_valid_session(self, db_client: TestClient) -> None:
        response = db_client.post("/auth/logout")

        assert response.status_code == 401


class TestEndAllSessions:
    def test_sessions_on_other_devices_stop_working(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US06-CA01"""
        user = create_user()
        this_device = authenticate_as(user)
        phone = authenticate_as(user)
        laptop = authenticate_as(user)

        response = db_client.delete("/auth/sessions", headers=this_device)

        assert response.status_code == 204
        assert db_client.get("/auth/me", headers=phone).status_code == 401
        assert db_client.get("/auth/me", headers=laptop).status_code == 401

    def test_current_session_also_stops_working(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        this_device = authenticate_as(create_user())

        db_client.delete("/auth/sessions", headers=this_device)

        assert db_client.get("/auth/me", headers=this_device).status_code == 401

    def test_sessions_of_other_users_are_not_affected(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        this_device = authenticate_as(create_user(email="ana@example.com"))
        someone_else = authenticate_as(create_user(email="bruno@example.com"))

        db_client.delete("/auth/sessions", headers=this_device)

        assert db_client.get("/auth/me", headers=someone_else).status_code == 200

    def test_ending_all_sessions_requires_a_valid_session(
        self, db_client: TestClient
    ) -> None:
        response = db_client.delete("/auth/sessions")

        assert response.status_code == 401


class TestExpiredCleanup:
    def test_expired_sessions_are_deleted(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        clock: FrozenClock,
        settings: Settings,
    ) -> None:
        user = create_user()
        authenticate_as(user)
        clock.advance(settings.session_duration)
        current = authenticate_as(user)

        result = delete_expired(
            db_session, clock, settings.password_reset_request_window
        )

        assert result.sessions == 1
        assert count_sessions(db_session) == 1
        assert db_client.get("/auth/me", headers=current).status_code == 200

    def test_reset_links_expired_over_a_day_ago_are_deleted(
        self,
        db_session: Session,
        create_user: CreateUser,
        clock: FrozenClock,
        settings: Settings,
    ) -> None:
        user = create_user()
        add_reset_link(db_session, user, expired_ago=timedelta(hours=24, seconds=1))
        add_reset_link(db_session, user, expired_ago=timedelta(hours=24))
        add_reset_link(db_session, user, expired_ago=timedelta(hours=1))

        result = delete_expired(
            db_session, clock, settings.password_reset_request_window
        )

        assert result.reset_links == 1
        assert count_reset_links(db_session) == 2

    def test_valid_reset_link_still_works(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        outbox: Outbox,
        clock: FrozenClock,
        settings: Settings,
    ) -> None:
        create_user(email="ana@example.com")
        request_reset(db_client, "ana@example.com")

        delete_expired(db_session, clock, settings.password_reset_request_window)

        assert reset_password(db_client, token_in(outbox)).status_code == 204

    def test_kept_links_still_count_towards_the_request_limit(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        outbox: Outbox,
        clock: FrozenClock,
        settings: Settings,
    ) -> None:
        create_user(email="ana@example.com")
        for _ in range(settings.password_reset_max_requests):
            request_reset(db_client, "ana@example.com")

        # Each request expired the previous link, so only the last one is valid.
        delete_expired(db_session, clock, settings.password_reset_request_window)
        request_reset(db_client, "ana@example.com")

        assert len(outbox.messages) == settings.password_reset_max_requests

    def test_retention_follows_a_request_window_longer_than_a_day(
        self, db_session: Session, create_user: CreateUser, clock: FrozenClock
    ) -> None:
        add_reset_link(db_session, create_user(), expired_ago=timedelta(hours=30))

        result = delete_expired(db_session, clock, timedelta(hours=48))

        assert result.reset_links == 0
        assert count_reset_links(db_session) == 1

    def test_command_line_deletes_the_expired_rows(
        self,
        db_session: Session,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        clock: FrozenClock,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Runs the module as `python -m advocondo.auth.cleanup` does."""
        user = create_user()
        authenticate_as(user)
        add_reset_link(db_session, user, expired_ago=timedelta(days=2))
        clock.advance(timedelta(days=60))
        monkeypatch.setattr(
            advocondo.db, "get_sessionmaker", lambda: lambda: nullcontext(db_session)
        )
        monkeypatch.setattr(advocondo.common.clock, "get_clock", lambda: clock)
        # A fresh import, as the interpreter does when running the module as a script.
        monkeypatch.delitem(sys.modules, "advocondo.auth.cleanup")

        runpy.run_module("advocondo.auth.cleanup", run_name="__main__")

        assert count_sessions(db_session) == 0
        assert count_reset_links(db_session) == 0
        assert "1 sessões e 1 links de redefinição" in capsys.readouterr().out
