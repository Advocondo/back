import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from advocondo.common.email import EmailMessage
from advocondo.common.passwords import get_password_hasher
from advocondo.users.errors import (
    AdminRoleNotAllowedError,
    EmailAlreadyInUseError,
    OabNumberNotAllowedError,
    OabNumberRequiredError,
)
from advocondo.users.models import Role, User, UserInvite, UserStatus
from advocondo.users.service import InviteDetails, InviteService


class TestUser:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            pytest.param(UserStatus.ACTIVE, True, id="active"),
            pytest.param(UserStatus.PENDING, False, id="pending-invite"),
            pytest.param(UserStatus.INACTIVE, False, id="inactive-US02-CA03"),
        ],
    )
    def test_only_active_users_can_log_in(
        self, status: UserStatus, expected: bool
    ) -> None:
        user = User(
            email="ana@example.com", name="Ana", role=Role.CLIENT, status=status
        )

        assert user.can_log_in is expected


class TestUserInvite:
    def test_invite_is_not_expired_before_its_expiration(self) -> None:
        invite = UserInvite(
            user_id=uuid.uuid4(),
            token_hash="a" * 64,
            expires_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
        )

        assert invite.is_expired(datetime(2026, 3, 2, 8, 59, tzinfo=UTC)) is False

    def test_invite_is_expired_at_the_exact_expiration_time(self) -> None:
        invite = UserInvite(
            user_id=uuid.uuid4(),
            token_hash="a" * 64,
            expires_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
        )

        assert invite.is_expired(datetime(2026, 3, 2, 9, 0, tzinfo=UTC)) is True


class FakeSession:
    def commit(self) -> None:
        pass


class FakeUserRepository:
    def __init__(self, existing: dict[str, User] | None = None) -> None:
        self.existing = existing or {}
        self.added: list[User] = []

    def get_by_email(self, email: str) -> User | None:
        return self.existing.get(email)

    def add(self, user: User) -> None:
        self.added.append(user)


class FakeInviteRepository:
    def __init__(self) -> None:
        self.added: list[UserInvite] = []

    def add(self, invite: UserInvite) -> None:
        self.added.append(invite)


class FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


class FrozenNow:
    def now(self) -> datetime:
        return datetime(2026, 3, 2, 9, 0, tzinfo=UTC)


def build_invite_service(
    existing: dict[str, User] | None = None,
) -> tuple[InviteService, FakeUserRepository, FakeInviteRepository, FakeEmailSender]:
    users = FakeUserRepository(existing)
    invites = FakeInviteRepository()
    sender = FakeEmailSender()
    service = InviteService(
        session=FakeSession(),  # type: ignore[arg-type]
        users=users,  # type: ignore[arg-type]
        invites=invites,  # type: ignore[arg-type]
        password_hasher=get_password_hasher(),
        email_sender=sender,
        clock=FrozenNow(),
        invite_link_duration=timedelta(hours=24),
        frontend_url="http://localhost:3000",
    )
    return service, users, invites, sender


def build_admin() -> User:
    return User(
        id=uuid.uuid4(),
        email="admin@example.com",
        name="Admin",
        role=Role.ADMIN,
        status=UserStatus.ACTIVE,
        password_hash="hash",
    )


def build_details(**overrides: Any) -> InviteDetails:
    fields: dict[str, Any] = {
        "email": "novo@example.com",
        "name": "Novo Colaborador",
        "role": Role.OPERATOR,
        "is_lawyer": False,
        "oab_number": None,
    }
    return InviteDetails(**(fields | overrides))


class TestInviteServiceRules:
    def test_cannot_invite_another_administrator(self) -> None:
        service, users, _, _ = build_invite_service()

        with pytest.raises(AdminRoleNotAllowedError):
            service.invite(build_admin(), build_details(role=Role.ADMIN))

        assert users.added == []

    def test_lawyer_must_inform_the_oab_number(self) -> None:
        service, users, _, _ = build_invite_service()

        with pytest.raises(OabNumberRequiredError):
            service.invite(build_admin(), build_details(is_lawyer=True))

        assert users.added == []

    def test_non_lawyer_cannot_inform_the_oab_number(self) -> None:
        service, users, _, _ = build_invite_service()

        with pytest.raises(OabNumberNotAllowedError):
            service.invite(
                build_admin(),
                build_details(is_lawyer=False, oab_number="123456/SP"),
            )

        assert users.added == []

    def test_email_already_registered_is_refused(self) -> None:
        service, users, _, _ = build_invite_service(
            existing={"novo@example.com": build_admin()}
        )

        with pytest.raises(EmailAlreadyInUseError):
            service.invite(build_admin(), build_details())

        assert users.added == []

    def test_invite_stores_pending_user_and_sends_email(self) -> None:
        service, users, invites, sender = build_invite_service()

        user = service.invite(
            build_admin(),
            build_details(
                email="Novo@Example.com",
                name="  Novo Colaborador  ",
                is_lawyer=True,
                oab_number="123456/SP",
            ),
        )

        assert user.email == "novo@example.com"
        assert user.name == "Novo Colaborador"
        assert user.status == UserStatus.PENDING
        assert user.is_lawyer is True
        assert user.oab_number == "123456/SP"
        assert user.password_hash is None
        assert users.added == [user]
        assert len(invites.added) == 1
        assert invites.added[0].user is user
        assert len(sender.sent) == 1
        assert sender.sent[0].to == "novo@example.com"
