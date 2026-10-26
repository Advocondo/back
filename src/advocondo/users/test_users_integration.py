import re
import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from advocondo.common.passwords import MAX_PASSWORD_LENGTH
from advocondo.common.tokens import hash_token
from advocondo.config import Settings, get_settings
from advocondo.main import app
from advocondo.users.models import (
    AuditAction,
    Role,
    User,
    UserCondominium,
    UserInvite,
    UserStatus,
)
from advocondo.users.repository import UserCondominiumRepository
from tests.fixtures.auth import AuthenticateAs
from tests.fixtures.condominios import CreateCondominium
from tests.fixtures.users import DEFAULT_PASSWORD, CreateUser
from tests.support.clock import FrozenClock
from tests.support.email import Outbox
from tests.support.settings import make_settings

PASSWORD = "senha-do-admin"
SETUP_TOKEN = "token-de-configuracao-usado-so-nos-testes"  # gitleaks:allow
FIRST_ADMIN = {"email": "Ana@Example.com", "name": "Ana Souza", "password": PASSWORD}
NEW_PASSWORD = "nova-senha-segura"  # gitleaks:allow (test-only password)
INVITE_PASSWORD = "senha-do-convidado"  # gitleaks:allow (test-only password)


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


def invite_user(
    client: TestClient, headers: dict[str, str], **overrides: Any
) -> httpx.Response:
    body: dict[str, Any] = {
        "email": "novo@example.com",
        "name": "Novo Colaborador",
        "role": Role.OPERATOR.value,
    }
    body.update(overrides)
    response: httpx.Response = client.post("/users/invites", json=body, headers=headers)
    return response


def accept_invite(
    client: TestClient, token: str, password: str = INVITE_PASSWORD
) -> httpx.Response:
    response: httpx.Response = client.post(
        "/users/invites/accept", json={"token": token, "password": password}
    )
    return response


def extract_token(body: str) -> str:
    match = re.search(r"[?&]token=([A-Za-z0-9_\-]+)", body)
    assert match is not None, "e-mail de convite não contém token"
    return match.group(1)


def invite_as_admin(
    client: TestClient,
    create_user: CreateUser,
    authenticate_as: AuthenticateAs,
) -> tuple[dict[str, str], User]:
    admin = create_user(role=Role.ADMIN)
    return authenticate_as(admin), admin


def change_role(
    client: TestClient,
    headers: dict[str, str],
    user_id: uuid.UUID,
    role: str,
) -> httpx.Response:
    response: httpx.Response = client.patch(
        f"/users/{user_id}/role", json={"role": role}, headers=headers
    )
    return response


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

    def test_lawyer_must_have_an_oab_number(self, db_session: Session) -> None:
        db_session.add(build_user(is_lawyer=True, oab_number=None))

        with pytest.raises(
            IntegrityError, match="ck_users_lawyer_has_valid_oab_number"
        ):
            db_session.flush()

    def test_non_lawyer_cannot_have_an_oab_number(self, db_session: Session) -> None:
        db_session.add(build_user(is_lawyer=False, oab_number="123456/SP"))

        with pytest.raises(
            IntegrityError, match="ck_users_lawyer_has_valid_oab_number"
        ):
            db_session.flush()


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


class TestInviteUser:
    def test_admin_can_invite_an_operator(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US07-CA01"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)

        response = invite_user(db_client, headers)

        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "novo@example.com"
        assert body["name"] == "Novo Colaborador"
        assert body["role"] == Role.OPERATOR.value
        assert body["status"] == UserStatus.PENDING.value
        assert body["is_lawyer"] is False
        assert body["oab_number"] is None

    def test_admin_can_invite_a_client(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US07-CA01"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)

        response = invite_user(db_client, headers, role=Role.CLIENT.value)

        assert response.status_code == 201
        assert response.json()["role"] == Role.CLIENT.value

    def test_invited_user_is_stored_as_pending(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US07-CA01"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)

        invite_user(db_client, headers)

        user = db_session.scalar(select(User).where(User.email == "novo@example.com"))
        assert user is not None
        assert user.status == UserStatus.PENDING
        assert user.password_hash is None

    def test_invite_sends_email_with_token(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        outbox: Outbox,
    ) -> None:
        """US07-CA03"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)

        invite_user(db_client, headers)

        assert len(outbox.messages) == 1
        message = outbox.messages[0]
        assert message.to == "novo@example.com"
        token = extract_token(message.body)
        invite = db_session.scalar(select(UserInvite))
        assert invite is not None
        assert invite.token_hash == hash_token(token)

    def test_invite_records_who_invited(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, admin = invite_as_admin(db_client, create_user, authenticate_as)

        invite_user(db_client, headers)

        invite = db_session.scalar(select(UserInvite))
        assert invite is not None
        assert invite.invited_by_id == admin.id

    def test_invite_requires_authentication(self, db_client: TestClient) -> None:
        """US07-CA02"""
        response = db_client.post(
            "/users/invites",
            json={
                "email": "novo@example.com",
                "name": "Novo Colaborador",
                "role": Role.OPERATOR.value,
            },
        )

        assert response.status_code == 401

    @pytest.mark.parametrize(
        "role",
        [
            pytest.param(Role.OPERATOR, id="operator"),
            pytest.param(Role.CLIENT, id="client"),
        ],
    )
    def test_only_admin_can_invite(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        role: Role,
    ) -> None:
        """US07-CA02"""
        headers = authenticate_as(create_user(role=role))

        response = invite_user(db_client, headers)

        assert response.status_code == 403
        assert response.json() == {
            "detail": "Você não tem permissão para esta operação."
        }

    def test_cannot_invite_another_admin(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)

        response = invite_user(db_client, headers, role=Role.ADMIN.value)

        assert response.status_code == 422
        assert response.json() == {
            "detail": "Não é possível convidar outro Administrador."
        }

    def test_email_must_be_unique(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US07-CA03"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        create_user(email="novo@example.com")

        response = invite_user(db_client, headers)

        assert response.status_code == 409
        assert response.json() == {
            "detail": "Este e-mail já está em uso por outro usuário."
        }

    def test_email_case_is_ignored_when_checking_duplicates(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US07-CA03"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        create_user(email="novo@example.com")

        response = invite_user(db_client, headers, email="NOVO@example.com")

        assert response.status_code == 409

    def test_lawyer_invitation_stores_the_oab_number(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US07-CA04"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)

        response = invite_user(
            db_client, headers, is_lawyer=True, oab_number="123456/SP"
        )

        assert response.status_code == 201
        body = response.json()
        assert body["is_lawyer"] is True
        assert body["oab_number"] == "123456/SP"

    def test_lawyer_marking_is_independent_of_the_role(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US07-CA04"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)

        response = invite_user(
            db_client,
            headers,
            role=Role.OPERATOR.value,
            is_lawyer=True,
            oab_number="123456/SP",
        )

        assert response.status_code == 201
        body = response.json()
        assert body["role"] == Role.OPERATOR.value
        assert body["is_lawyer"] is True

    def test_lawyer_without_the_oab_number_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US07-CA04"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)

        response = invite_user(db_client, headers, is_lawyer=True)

        assert response.status_code == 422
        assert response.json() == {
            "detail": "Informe o número da OAB para marcar o usuário como advogado."
        }

    @pytest.mark.parametrize(
        ("oab_number", "error_type"),
        [
            pytest.param("1234567", "string_too_short", id="too-short"),
            pytest.param("1234567890123", "string_too_long", id="too-long"),
        ],
    )
    def test_lawyer_with_invalid_oab_number_length_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        oab_number: str,
        error_type: str,
    ) -> None:
        """US07-CA04"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)

        response = invite_user(
            db_client, headers, is_lawyer=True, oab_number=oab_number
        )

        assert response.status_code == 422
        assert response.json()["detail"][0]["type"] == error_type

    def test_non_lawyer_with_the_oab_number_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US07-CA04"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)

        response = invite_user(db_client, headers, oab_number="123456/SP")

        assert response.status_code == 422
        assert response.json() == {
            "detail": "O número da OAB só pode ser informado para advogados."
        }

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({"email": "sem-arroba"}, id="bad-email"),
            pytest.param({"email": ""}, id="empty-email"),
            pytest.param({"name": "   "}, id="blank-name"),
            pytest.param({"role": "invalid"}, id="bad-role"),
        ],
    )
    def test_invalid_payload_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        payload: dict[str, str],
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)

        response = invite_user(db_client, headers, **payload)

        assert response.status_code == 422


class TestAcceptInvite:
    def _invite(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        outbox: Outbox,
        **payload: Any,
    ) -> str:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        invite_user(db_client, headers, **payload)
        assert len(outbox.messages) == 1
        return extract_token(outbox.messages[0].body)

    def test_invited_user_can_accept_and_log_in(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        outbox: Outbox,
    ) -> None:
        """US07-CA01"""
        token = self._invite(db_client, create_user, authenticate_as, outbox)

        response = accept_invite(db_client, token)

        assert response.status_code == 200
        assert response.json()["status"] == UserStatus.ACTIVE.value
        assert log_in(db_client, "novo@example.com", INVITE_PASSWORD) == 200

    def test_accepting_the_invite_deletes_the_invite_row(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        outbox: Outbox,
    ) -> None:
        token = self._invite(db_client, create_user, authenticate_as, outbox)

        accept_invite(db_client, token)

        assert db_session.scalar(select(UserInvite)) is None

    def test_accepting_the_same_invite_twice_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        outbox: Outbox,
    ) -> None:
        token = self._invite(db_client, create_user, authenticate_as, outbox)
        accept_invite(db_client, token)

        response = accept_invite(db_client, token)

        assert response.status_code == 422
        assert response.json() == {"detail": "O convite é inválido ou já expirou."}

    def test_invalid_token_is_refused(self, db_client: TestClient) -> None:
        response = accept_invite(db_client, "token-que-nao-existe")

        assert response.status_code == 422
        assert response.json() == {"detail": "O convite é inválido ou já expirou."}

    def test_expired_invite_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        outbox: Outbox,
        clock: FrozenClock,
    ) -> None:
        token = self._invite(db_client, create_user, authenticate_as, outbox)
        clock.advance(timedelta(days=2))

        response = accept_invite(db_client, token)

        assert response.status_code == 422
        assert response.json() == {"detail": "O convite é inválido ou já expirou."}

    def test_short_password_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        outbox: Outbox,
    ) -> None:
        token = self._invite(db_client, create_user, authenticate_as, outbox)

        response = accept_invite(db_client, token, password="curta")

        assert response.status_code == 422
        assert response.json() == {
            "detail": "A senha precisa ter pelo menos 8 caracteres."
        }

    def test_lawyer_information_survives_the_acceptance(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        outbox: Outbox,
    ) -> None:
        """US07-CA04"""
        token = self._invite(
            db_client,
            create_user,
            authenticate_as,
            outbox,
            is_lawyer=True,
            oab_number="123456/SP",
        )

        response = accept_invite(db_client, token)

        assert response.status_code == 200
        body = response.json()
        assert body["is_lawyer"] is True
        assert body["oab_number"] == "123456/SP"


class TestChangeUserRole:
    def test_admin_changes_operator_to_client(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US09-CA01"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="target@example.com", role=Role.OPERATOR)

        response = change_role(db_client, headers, target.id, Role.CLIENT.value)

        assert response.status_code == 200
        assert response.json()["role"] == Role.CLIENT.value

    def test_admin_changes_client_to_operator(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US09-CA01"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="target@example.com", role=Role.CLIENT)

        response = change_role(db_client, headers, target.id, Role.OPERATOR.value)

        assert response.status_code == 200
        assert response.json()["role"] == Role.OPERATOR.value

    def test_admin_promotes_operator_to_administrator(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US09-CA01"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="target@example.com", role=Role.OPERATOR)

        response = change_role(db_client, headers, target.id, Role.ADMIN.value)

        assert response.status_code == 200
        assert response.json()["role"] == Role.ADMIN.value

    @pytest.mark.parametrize(
        "role",
        [
            pytest.param(Role.OPERATOR, id="operator"),
            pytest.param(Role.CLIENT, id="client"),
        ],
    )
    def test_only_admin_can_change_role(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        role: Role,
    ) -> None:
        """US09-CA02"""
        headers = authenticate_as(create_user(role=role))
        target = create_user(email="target@example.com", role=Role.OPERATOR)

        response = change_role(db_client, headers, target.id, Role.CLIENT.value)

        assert response.status_code == 403
        assert response.json() == {
            "detail": "Você não tem permissão para esta operação."
        }

    def test_change_role_requires_authentication(
        self,
        db_client: TestClient,
        create_user: CreateUser,
    ) -> None:
        """US09-CA02"""
        target = create_user(email="target@example.com", role=Role.OPERATOR)

        response = db_client.patch(
            f"/users/{target.id}/role", json={"role": Role.CLIENT.value}
        )

        assert response.status_code == 401

    def test_admin_cannot_change_own_role(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        admin = create_user(role=Role.ADMIN)
        headers = authenticate_as(admin)

        response = change_role(db_client, headers, admin.id, Role.OPERATOR.value)

        assert response.status_code == 422
        assert response.json() == {
            "detail": "Você não pode alterar o seu próprio perfil."
        }

    def test_admin_can_confirm_own_role_without_change(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        admin = create_user(role=Role.ADMIN)
        headers = authenticate_as(admin)

        response = change_role(db_client, headers, admin.id, Role.ADMIN.value)

        assert response.status_code == 200
        assert response.json()["role"] == Role.ADMIN.value

    def test_invalid_user_returns_404(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)

        response = change_role(db_client, headers, uuid.uuid4(), Role.CLIENT.value)

        assert response.status_code == 404
        assert response.json() == {"detail": "Usuário não encontrado."}

    @pytest.mark.parametrize(
        "invalid_role",
        [
            pytest.param("superadmin", id="unknown-role"),
            pytest.param("", id="empty"),
        ],
    )
    def test_invalid_role_payload_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        invalid_role: str,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="target@example.com", role=Role.OPERATOR)

        response = change_role(db_client, headers, target.id, invalid_role)

        assert response.status_code == 422


def change_status(
    client: TestClient,
    headers: dict[str, str],
    user_id: uuid.UUID | str,
    status: str,
) -> httpx.Response:
    response: httpx.Response = client.patch(
        f"/users/{user_id}/status", json={"status": status}, headers=headers
    )
    return response


class TestChangeUserStatus:
    """US08: o Administrador inativa e reativa o acesso pela rota."""

    def test_admin_inactivates_a_user_right_away(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US08-CA01"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="target@example.com")

        response = change_status(db_client, headers, target.id, "inactive")

        assert response.status_code == 200
        assert response.json()["status"] == UserStatus.INACTIVE.value
        db_session.refresh(target)
        assert target.status == UserStatus.INACTIVE

    def test_inactivated_user_loses_the_open_session_and_cannot_log_in(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US08-CA02"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="target@example.com")
        target_headers = authenticate_as(target)
        assert db_client.get("/auth/me", headers=target_headers).status_code == 200

        change_status(db_client, headers, target.id, "inactive")

        assert db_client.get("/auth/me", headers=target_headers).status_code == 401
        assert log_in(db_client, "target@example.com", DEFAULT_PASSWORD) == 401

    def test_inactivation_can_be_reversed(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US08-CA03"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="target@example.com", status=UserStatus.INACTIVE)

        response = change_status(db_client, headers, target.id, "active")

        assert response.status_code == 200
        assert response.json()["status"] == UserStatus.ACTIVE.value
        assert log_in(db_client, "target@example.com", DEFAULT_PASSWORD) == 200

    def test_unknown_user_is_not_found(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)

        response = change_status(db_client, headers, uuid.uuid4(), "inactive")

        assert response.status_code == 404
        assert response.json() == {"detail": "Usuário não encontrado."}

    def test_pending_user_cannot_change_status(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """Quem tem convite pendente ainda não tem acesso para inativar."""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(
            email="target@example.com", status=UserStatus.PENDING, password=None
        )

        response = change_status(db_client, headers, target.id, "inactive")

        assert response.status_code == 422
        assert response.json() == {
            "detail": "Usuário com convite pendente precisa aceitar o convite antes."
        }

    def test_admin_cannot_inactivate_themselves(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """Evita que o escritório fique sem Administrador por engano."""
        headers, admin = invite_as_admin(db_client, create_user, authenticate_as)

        response = change_status(db_client, headers, admin.id, "inactive")

        assert response.status_code == 422
        assert response.json() == {
            "detail": "Você não pode inativar o seu próprio acesso."
        }

    @pytest.mark.parametrize(
        "status",
        [
            pytest.param("pending", id="pending"),
            pytest.param("blocked", id="unknown"),
        ],
    )
    def test_only_active_or_inactive_is_accepted(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        status: str,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="target@example.com")

        response = change_status(db_client, headers, target.id, status)

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "role",
        [
            pytest.param(Role.OPERATOR, id="operator"),
            pytest.param(Role.CLIENT, id="client"),
        ],
    )
    def test_only_the_admin_changes_status(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        role: Role,
    ) -> None:
        headers = authenticate_as(create_user(email="someone@example.com", role=role))
        target = create_user(email="target@example.com")

        response = change_status(db_client, headers, target.id, "inactive")

        assert response.status_code == 403

    def test_requires_a_session(
        self, db_client: TestClient, create_user: CreateUser
    ) -> None:
        target = create_user(email="target@example.com")

        response = db_client.patch(
            f"/users/{target.id}/status", json={"status": "inactive"}
        )

        assert response.status_code == 401


class TestUserHistory:
    def test_history_records_invite(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US11-CA01"""
        headers, admin = invite_as_admin(db_client, create_user, authenticate_as)

        response = invite_user(db_client, headers)
        user_id = response.json()["id"]

        history_response = db_client.get(f"/users/{user_id}/history", headers=headers)

        assert history_response.status_code == 200
        logs = history_response.json()["logs"]
        assert len(logs) == 1
        assert logs[0]["action"] == AuditAction.INVITED.value
        assert logs[0]["actor"]["id"] == str(admin.id)
        assert logs[0]["old_value"] is None
        assert logs[0]["new_value"] == Role.OPERATOR.value
        assert "created_at" in logs[0]

    def test_history_records_role_change(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US11-CA01"""
        headers, admin = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="target@example.com", role=Role.OPERATOR)

        change_role(db_client, headers, target.id, Role.CLIENT.value)

        history_response = db_client.get(f"/users/{target.id}/history", headers=headers)
        logs = history_response.json()["logs"]

        assert len(logs) == 1
        assert logs[0]["action"] == AuditAction.ROLE_CHANGED.value
        assert logs[0]["actor"]["id"] == str(admin.id)
        assert logs[0]["old_value"] == Role.OPERATOR.value
        assert logs[0]["new_value"] == Role.CLIENT.value

    def test_history_records_status_change(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US11-CA01"""
        headers, admin = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="target@example.com", status=UserStatus.ACTIVE)

        db_client.patch(
            f"/users/{target.id}/status",
            json={"status": UserStatus.INACTIVE.value},
            headers=headers,
        )

        history_response = db_client.get(f"/users/{target.id}/history", headers=headers)
        logs = history_response.json()["logs"]

        assert len(logs) == 1
        assert logs[0]["action"] == AuditAction.STATUS_CHANGED.value
        assert logs[0]["actor"]["id"] == str(admin.id)
        assert logs[0]["old_value"] == UserStatus.ACTIVE.value
        assert logs[0]["new_value"] == UserStatus.INACTIVE.value

    def test_history_multiple_actions_in_order(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US11-CA01"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="target@example.com", role=Role.OPERATOR)

        change_role(db_client, headers, target.id, Role.CLIENT.value)
        db_client.patch(
            f"/users/{target.id}/status",
            json={"status": UserStatus.INACTIVE.value},
            headers=headers,
        )

        history_response = db_client.get(f"/users/{target.id}/history", headers=headers)
        logs = history_response.json()["logs"]

        assert len(logs) == 2
        assert logs[0]["action"] == AuditAction.STATUS_CHANGED.value
        assert logs[1]["action"] == AuditAction.ROLE_CHANGED.value

    @pytest.mark.parametrize(
        ("role", "email"),
        [
            pytest.param(Role.OPERATOR, "op@example.com", id="operator"),
            pytest.param(Role.CLIENT, "cli@example.com", id="client"),
        ],
    )
    def test_history_only_admin_can_view(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        role: Role,
        email: str,
    ) -> None:
        """US11-CA02"""
        target = create_user(email="target@example.com")
        headers = authenticate_as(create_user(role=role, email=email))

        response = db_client.get(f"/users/{target.id}/history", headers=headers)

        assert response.status_code == 403
        assert response.json() == {
            "detail": "Você não tem permissão para esta operação."
        }

    def test_history_requires_authentication(
        self,
        db_client: TestClient,
        create_user: CreateUser,
    ) -> None:
        """US11-CA02"""
        target = create_user(email="target@example.com")

        response = db_client.get(f"/users/{target.id}/history")

        assert response.status_code == 401

    def test_history_for_unknown_user_returns_404(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)

        response = db_client.get(f"/users/{uuid.uuid4()}/history", headers=headers)

        assert response.status_code == 404
        assert response.json() == {"detail": "Usuário não encontrado."}


def put_condominiums(
    client: TestClient, headers: dict[str, str], user: User, ids: list[uuid.UUID]
) -> httpx.Response:
    response: httpx.Response = client.put(
        f"/users/{user.id}/condominiums",
        json={"condominium_ids": [str(item) for item in ids]},
        headers=headers,
    )
    return response


def get_condominiums(
    client: TestClient, headers: dict[str, str], user: User
) -> httpx.Response:
    response: httpx.Response = client.get(
        f"/users/{user.id}/condominiums", headers=headers
    )
    return response


class TestLinkClientToCondominiums:
    def test_admin_links_a_client_to_condominiums(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US10-CA01"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        client_user = create_user(email="cliente@example.com", role=Role.CLIENT)
        mirante = create_condominium(name="Mirante")
        bosque = create_condominium(name="Bosque")

        response = put_condominiums(
            db_client, headers, client_user, [mirante.id, bosque.id]
        )

        assert response.status_code == 200
        expected = [
            {"id": str(bosque.id), "name": "Bosque"},
            {"id": str(mirante.id), "name": "Mirante"},
        ]
        assert response.json() == expected
        assert get_condominiums(db_client, headers, client_user).json() == expected

    def test_replacing_the_list_keeps_only_the_new_set(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US10-CA01"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        client_user = create_user(email="cliente@example.com", role=Role.CLIENT)
        first = create_condominium(name="Primeiro")
        second = create_condominium(name="Segundo")
        third = create_condominium(name="Terceiro")
        put_condominiums(db_client, headers, client_user, [first.id, second.id])

        response = put_condominiums(
            db_client, headers, client_user, [second.id, third.id]
        )

        assert [item["name"] for item in response.json()] == ["Segundo", "Terceiro"]

    def test_empty_list_unlinks_every_condominium(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US10-CA02"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        client_user = create_user(email="cliente@example.com", role=Role.CLIENT)
        put_condominiums(
            db_client, headers, client_user, [create_condominium(name="Mirante").id]
        )

        response = put_condominiums(db_client, headers, client_user, [])

        assert response.status_code == 200
        assert response.json() == []
        links = UserCondominiumRepository(db_session)
        assert links.condominium_ids_of(client_user.id) == set()

    def test_client_without_links_has_no_condominiums(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US10-CA02"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        client_user = create_user(email="cliente@example.com", role=Role.CLIENT)

        response = get_condominiums(db_client, headers, client_user)

        assert response.status_code == 200
        assert response.json() == []

    def test_client_sees_only_linked_condominiums(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US10-CA01 and US10-CA02: the set the Client panel (US37) filters by."""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        ana = create_user(email="ana.cliente@example.com", role=Role.CLIENT)
        beto = create_user(email="beto.cliente@example.com", role=Role.CLIENT)
        sem_vinculo = create_user(email="sem@example.com", role=Role.CLIENT)
        mirante = create_condominium(name="Mirante")
        bosque = create_condominium(name="Bosque")
        put_condominiums(db_client, headers, ana, [mirante.id])
        put_condominiums(db_client, headers, beto, [mirante.id, bosque.id])

        links = UserCondominiumRepository(db_session)

        assert links.condominium_ids_of(ana.id) == {mirante.id}
        assert links.condominium_ids_of(beto.id) == {mirante.id, bosque.id}
        assert links.condominium_ids_of(sem_vinculo.id) == set()

    def test_duplicated_ids_are_linked_once(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        client_user = create_user(email="cliente@example.com", role=Role.CLIENT)
        mirante = create_condominium(name="Mirante")

        response = put_condominiums(
            db_client, headers, client_user, [mirante.id, mirante.id]
        )

        assert response.status_code == 200
        assert response.json() == [{"id": str(mirante.id), "name": "Mirante"}]

    def test_replace_condominiums_rejects_unknown_condominium_without_saving(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        client_user = create_user(email="cliente@example.com", role=Role.CLIENT)
        kept = create_condominium(name="Mirante")
        put_condominiums(db_client, headers, client_user, [kept.id])
        unknown = uuid.uuid4()

        response = put_condominiums(
            db_client, headers, client_user, [create_condominium().id, unknown]
        )

        assert response.status_code == 422
        assert str(unknown) in response.json()["detail"]
        links = UserCondominiumRepository(db_session)
        assert links.condominium_ids_of(client_user.id) == {kept.id}

    @pytest.mark.parametrize("role", [Role.ADMIN, Role.OPERATOR])
    def test_only_clients_can_be_linked(
        self,
        role: Role,
        db_client: TestClient,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="outro@example.com", role=role)

        put_response = put_condominiums(
            db_client, headers, target, [create_condominium().id]
        )
        get_response = get_condominiums(db_client, headers, target)

        expected = {
            "detail": "Somente usuários com perfil Cliente têm condomínios vinculados."
        }
        assert put_response.status_code == 422
        assert put_response.json() == expected
        assert get_response.status_code == 422
        assert get_response.json() == expected

    @pytest.mark.parametrize("status", [UserStatus.INACTIVE, UserStatus.PENDING])
    def test_inactive_and_pending_clients_can_be_linked(
        self,
        status: UserStatus,
        db_client: TestClient,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        client_user = create_user(
            email="cliente@example.com",
            role=Role.CLIENT,
            status=status,
            password=None if status == UserStatus.PENDING else DEFAULT_PASSWORD,
        )

        response = put_condominiums(
            db_client, headers, client_user, [create_condominium().id]
        )

        assert response.status_code == 200

    def test_unknown_user_is_not_found(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        ghost = User(id=uuid.uuid4())

        assert put_condominiums(db_client, headers, ghost, []).status_code == 404
        assert get_condominiums(db_client, headers, ghost).status_code == 404

    @pytest.mark.parametrize("role", [Role.OPERATOR, Role.CLIENT])
    def test_only_the_admin_can_manage_the_links(
        self,
        role: Role,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        caller = create_user(email="chamador@example.com", role=role)
        client_user = create_user(email="cliente@example.com", role=Role.CLIENT)
        headers = authenticate_as(caller)

        assert put_condominiums(db_client, headers, client_user, []).status_code == 403
        assert get_condominiums(db_client, headers, client_user).status_code == 403

    def test_requests_without_login_are_refused(
        self, db_client: TestClient, create_user: CreateUser
    ) -> None:
        client_user = create_user(email="cliente@example.com", role=Role.CLIENT)

        assert put_condominiums(db_client, {}, client_user, []).status_code == 401
        assert get_condominiums(db_client, {}, client_user).status_code == 401

    def test_invalid_payload_is_refused(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        client_user = create_user(email="cliente@example.com", role=Role.CLIENT)
        url = f"/users/{client_user.id}/condominiums"

        not_a_uuid = db_client.put(
            url, json={"condominium_ids": ["abc"]}, headers=headers
        )
        missing_field = db_client.put(url, json={}, headers=headers)
        extra_field = db_client.put(
            url, json={"condominium_ids": [], "role": "admin"}, headers=headers
        )

        assert not_a_uuid.status_code == 422
        assert missing_field.status_code == 422
        assert extra_field.status_code == 422

    def test_links_are_dropped_when_the_client_changes_role(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """A user made a Client again must not get back the old access."""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="cliente@example.com", role=Role.CLIENT)
        other = create_user(email="outro@example.com", role=Role.CLIENT)
        mirante = create_condominium(name="Mirante")
        put_condominiums(db_client, headers, target, [mirante.id])
        put_condominiums(db_client, headers, other, [mirante.id])

        to_operator = change_role(db_client, headers, target.id, Role.OPERATOR.value)
        back_to_client = change_role(db_client, headers, target.id, Role.CLIENT.value)

        assert to_operator.status_code == 200
        assert back_to_client.status_code == 200
        links = UserCondominiumRepository(db_session)
        assert links.condominium_ids_of(target.id) == set()
        assert links.condominium_ids_of(other.id) == {mirante.id}

    def test_links_are_kept_when_the_role_stays_client(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="cliente@example.com", role=Role.CLIENT)
        mirante = create_condominium(name="Mirante")
        put_condominiums(db_client, headers, target, [mirante.id])

        response = change_role(db_client, headers, target.id, Role.CLIENT.value)

        assert response.status_code == 200
        links = UserCondominiumRepository(db_session)
        assert links.condominium_ids_of(target.id) == {mirante.id}

    def test_links_are_kept_when_the_client_is_deactivated_and_reactivated(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="cliente@example.com", role=Role.CLIENT)
        mirante = create_condominium(name="Mirante")
        put_condominiums(db_client, headers, target, [mirante.id])
        url = f"/users/{target.id}/status"

        deactivated = db_client.patch(
            url, json={"status": UserStatus.INACTIVE.value}, headers=headers
        )
        reactivated = db_client.patch(
            url, json={"status": UserStatus.ACTIVE.value}, headers=headers
        )

        assert deactivated.status_code == 200
        assert reactivated.status_code == 200
        links = UserCondominiumRepository(db_session)
        assert links.condominium_ids_of(target.id) == {mirante.id}

    def test_links_are_deleted_with_the_user_and_with_the_condominium(
        self,
        db_client: TestClient,
        db_session: Session,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        gone_user = create_user(email="saiu@example.com", role=Role.CLIENT)
        kept_user = create_user(email="ficou@example.com", role=Role.CLIENT)
        gone_condominium = create_condominium(name="Demolido")
        kept_condominium = create_condominium(name="Mirante")
        both = [gone_condominium.id, kept_condominium.id]
        put_condominiums(db_client, headers, gone_user, both)
        put_condominiums(db_client, headers, kept_user, both)

        db_session.delete(gone_user)
        db_session.delete(gone_condominium)
        db_session.flush()
        db_session.expire_all()

        remaining = db_session.scalars(select(UserCondominium)).all()
        assert [(link.user_id, link.condominium_id) for link in remaining] == [
            (kept_user.id, kept_condominium.id)
        ]


def get_history(
    client: TestClient, headers: dict[str, str], user: User
) -> list[dict[str, Any]]:
    response = client.get(f"/users/{user.id}/history", headers=headers)
    assert response.status_code == 200
    logs: list[dict[str, Any]] = response.json()["logs"]
    return logs


class TestCondominiumsHistory:
    def test_linking_records_the_added_condominiums(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US11-CA01"""
        headers, admin = invite_as_admin(db_client, create_user, authenticate_as)
        client_user = create_user(email="cliente@example.com", role=Role.CLIENT)
        mirante = create_condominium(name="Mirante")
        bosque = create_condominium(name="Bosque")

        put_condominiums(db_client, headers, client_user, [mirante.id, bosque.id])

        logs = get_history(db_client, headers, client_user)
        assert len(logs) == 1
        assert logs[0]["action"] == AuditAction.CONDOMINIUMS_CHANGED.value
        assert logs[0]["actor"] == {"id": str(admin.id), "name": admin.name}
        assert logs[0]["old_value"] is None
        assert logs[0]["new_value"] is None
        assert logs[0]["added_condominiums"] == [
            {"id": str(bosque.id), "name": "Bosque"},
            {"id": str(mirante.id), "name": "Mirante"},
        ]
        assert logs[0]["removed_condominiums"] == []
        assert "created_at" in logs[0]

    def test_replacing_records_only_the_difference(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US11-CA01"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        client_user = create_user(email="cliente@example.com", role=Role.CLIENT)
        first = create_condominium(name="Primeiro")
        second = create_condominium(name="Segundo")
        third = create_condominium(name="Terceiro")
        put_condominiums(db_client, headers, client_user, [first.id, second.id])

        put_condominiums(db_client, headers, client_user, [second.id, third.id])

        logs = get_history(db_client, headers, client_user)
        assert len(logs) == 2
        assert logs[0]["added_condominiums"] == [
            {"id": str(third.id), "name": "Terceiro"}
        ]
        assert logs[0]["removed_condominiums"] == [
            {"id": str(first.id), "name": "Primeiro"}
        ]

    def test_unlinking_everything_records_the_removed_condominiums(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US11-CA01"""
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        client_user = create_user(email="cliente@example.com", role=Role.CLIENT)
        mirante = create_condominium(name="Mirante")
        put_condominiums(db_client, headers, client_user, [mirante.id])

        put_condominiums(db_client, headers, client_user, [])

        logs = get_history(db_client, headers, client_user)
        assert len(logs) == 2
        assert logs[0]["added_condominiums"] == []
        assert logs[0]["removed_condominiums"] == [
            {"id": str(mirante.id), "name": "Mirante"}
        ]

    def test_sending_the_same_set_records_nothing(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        client_user = create_user(email="cliente@example.com", role=Role.CLIENT)
        mirante = create_condominium(name="Mirante")
        bosque = create_condominium(name="Bosque")
        put_condominiums(db_client, headers, client_user, [mirante.id, bosque.id])

        response = put_condominiums(
            db_client, headers, client_user, [bosque.id, mirante.id, bosque.id]
        )

        assert response.status_code == 200
        assert len(get_history(db_client, headers, client_user)) == 1

    def test_empty_list_for_a_client_without_links_records_nothing(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        client_user = create_user(email="cliente@example.com", role=Role.CLIENT)

        response = put_condominiums(db_client, headers, client_user, [])

        assert response.status_code == 200
        assert get_history(db_client, headers, client_user) == []

    def test_refused_change_records_nothing(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        client_user = create_user(email="cliente@example.com", role=Role.CLIENT)
        mirante = create_condominium(name="Mirante")

        response = put_condominiums(
            db_client, headers, client_user, [mirante.id, uuid.uuid4()]
        )

        assert response.status_code == 422
        assert get_history(db_client, headers, client_user) == []

    def test_history_keeps_the_name_the_condominium_had(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        client_user = create_user(email="cliente@example.com", role=Role.CLIENT)
        mirante = create_condominium(name="Mirante")
        put_condominiums(db_client, headers, client_user, [mirante.id])

        rename = db_client.patch(
            f"/condominiums/{mirante.id}",
            json={"name": "Mirante do Vale"},
            headers=headers,
        )

        assert rename.status_code == 200
        logs = get_history(db_client, headers, client_user)
        assert logs[0]["added_condominiums"] == [
            {"id": str(mirante.id), "name": "Mirante"}
        ]

    def test_role_change_records_the_dropped_links_after_the_role(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US11-CA01"""
        headers, admin = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="cliente@example.com", role=Role.CLIENT)
        mirante = create_condominium(name="Mirante")
        bosque = create_condominium(name="Bosque")
        put_condominiums(db_client, headers, target, [mirante.id, bosque.id])

        change_role(db_client, headers, target.id, Role.OPERATOR.value)

        logs = get_history(db_client, headers, target)
        assert [log["action"] for log in logs] == [
            AuditAction.CONDOMINIUMS_CHANGED.value,
            AuditAction.ROLE_CHANGED.value,
            AuditAction.CONDOMINIUMS_CHANGED.value,
        ]
        assert logs[0]["actor"]["id"] == str(admin.id)
        assert logs[0]["added_condominiums"] == []
        assert logs[0]["removed_condominiums"] == [
            {"id": str(bosque.id), "name": "Bosque"},
            {"id": str(mirante.id), "name": "Mirante"},
        ]
        assert logs[1]["old_value"] == Role.CLIENT.value
        assert logs[1]["new_value"] == Role.OPERATOR.value
        assert logs[1]["added_condominiums"] == []
        assert logs[1]["removed_condominiums"] == []

    def test_role_change_of_a_client_without_links_records_only_the_role(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="cliente@example.com", role=Role.CLIENT)

        change_role(db_client, headers, target.id, Role.OPERATOR.value)

        logs = get_history(db_client, headers, target)
        assert [log["action"] for log in logs] == [AuditAction.ROLE_CHANGED.value]

    def test_keeping_the_client_role_records_nothing_about_links(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        create_condominium: CreateCondominium,
        authenticate_as: AuthenticateAs,
    ) -> None:
        headers, _ = invite_as_admin(db_client, create_user, authenticate_as)
        target = create_user(email="cliente@example.com", role=Role.CLIENT)
        put_condominiums(
            db_client, headers, target, [create_condominium(name="Mirante").id]
        )

        change_role(db_client, headers, target.id, Role.CLIENT.value)

        assert len(get_history(db_client, headers, target)) == 1


class TestListLawyers:
    def test_lists_only_active_lawyers_ordered_by_name(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
    ) -> None:
        """US18-CA01"""
        operator = create_user(email="operador@example.com", name="Operador")
        zeca = create_user(
            email="zeca@example.com",
            name="Zeca Lima",
            is_lawyer=True,
            oab_number="123456/SP",
        )
        bia = create_user(
            email="bia@example.com",
            name="Bia Costa",
            is_lawyer=True,
            oab_number="654321/DF",
        )
        create_user(email="ana@example.com", name="Ana Souza")
        create_user(
            email="pendente@example.com",
            name="Pendente",
            is_lawyer=True,
            oab_number="111111/GO",
            status=UserStatus.PENDING,
            password=None,
        )
        create_user(
            email="inativo@example.com",
            name="Inativo",
            is_lawyer=True,
            oab_number="222222/MG",
            status=UserStatus.INACTIVE,
        )

        response = db_client.get("/users/lawyers", headers=authenticate_as(operator))

        assert response.status_code == 200
        assert response.json() == [
            {"id": str(bia.id), "name": "Bia Costa", "oab_number": "654321/DF"},
            {"id": str(zeca.id), "name": "Zeca Lima", "oab_number": "123456/SP"},
        ]

    @pytest.mark.parametrize(
        ("role", "expected_status"),
        [
            pytest.param(Role.ADMIN, 200, id="admin"),
            pytest.param(Role.OPERATOR, 200, id="operator"),
            pytest.param(Role.CLIENT, 403, id="client"),
        ],
    )
    def test_only_administrators_and_operators_can_list_lawyers(
        self,
        db_client: TestClient,
        create_user: CreateUser,
        authenticate_as: AuthenticateAs,
        role: Role,
        expected_status: int,
    ) -> None:
        """US18-CA01"""
        user = create_user(role=role)

        response = db_client.get("/users/lawyers", headers=authenticate_as(user))

        assert response.status_code == expected_status

    def test_request_without_a_token_is_refused(self, db_client: TestClient) -> None:
        """US18-CA01"""
        response = db_client.get("/users/lawyers")

        assert response.status_code == 401
