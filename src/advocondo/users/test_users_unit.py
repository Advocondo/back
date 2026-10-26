import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from advocondo.common.email import EmailMessage
from advocondo.common.passwords import get_password_hasher
from advocondo.condominios.models import Condominium
from advocondo.users.errors import (
    AdminRoleNotAllowedError,
    EmailAlreadyInUseError,
    OabNumberNotAllowedError,
    OabNumberRequiredError,
)
from advocondo.users.models import (
    AuditAction,
    Role,
    User,
    UserAuditLog,
    UserInvite,
    UserStatus,
)
from advocondo.users.schemas import InviteUserRequest
from advocondo.users.service import (
    InviteDetails,
    InviteService,
    build_condominiums_change_log,
)


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

    @pytest.mark.parametrize(
        ("is_lawyer", "status", "expected"),
        [
            pytest.param(True, UserStatus.ACTIVE, True, id="active-lawyer"),
            pytest.param(True, UserStatus.PENDING, False, id="pending-lawyer"),
            pytest.param(True, UserStatus.INACTIVE, False, id="inactive-lawyer"),
            pytest.param(False, UserStatus.ACTIVE, False, id="active-non-lawyer"),
        ],
    )
    def test_only_active_lawyers_can_be_responsible_for_an_acordo(
        self, is_lawyer: bool, status: UserStatus, expected: bool
    ) -> None:
        """US18-CA01"""
        user = User(
            email="ana@example.com",
            name="Ana",
            role=Role.OPERATOR,
            status=status,
            is_lawyer=is_lawyer,
        )

        assert user.can_be_responsible_lawyer is expected


class TestUserInvite:
    @pytest.mark.parametrize(
        ("now", "expired"),
        [
            pytest.param(datetime(2026, 3, 2, 8, 59, tzinfo=UTC), False, id="before"),
            pytest.param(datetime(2026, 3, 2, 9, 0, tzinfo=UTC), True, id="exact-time"),
            pytest.param(datetime(2026, 3, 2, 9, 1, tzinfo=UTC), True, id="after"),
        ],
    )
    def test_invite_expires_at_the_exact_expiration_time(
        self, now: datetime, expired: bool
    ) -> None:
        invite = UserInvite(
            user_id=uuid.uuid4(),
            token_hash="a" * 64,
            expires_at=datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
        )

        assert invite.is_expired(now) is expired


class TestCondominiumsChangeLog:
    def test_same_set_builds_no_log(self) -> None:
        mirante = Condominium(id=uuid.uuid4(), name="Mirante")
        admin = User(email="admin@example.com", name="Admin", role=Role.ADMIN)
        client = User(email="cliente@example.com", name="Cliente", role=Role.CLIENT)

        log = build_condominiums_change_log(client, admin, [mirante], [mirante])

        assert log is None

    def test_log_holds_the_added_and_removed_condominiums(self) -> None:
        kept = Condominium(id=uuid.uuid4(), name="Bosque")
        removed = Condominium(id=uuid.uuid4(), name="Mirante")
        added = Condominium(id=uuid.uuid4(), name="Vale")
        admin = User(email="admin@example.com", name="Admin", role=Role.ADMIN)
        client = User(email="cliente@example.com", name="Cliente", role=Role.CLIENT)

        log = build_condominiums_change_log(
            client, admin, [kept, removed], [kept, added]
        )

        assert log is not None
        assert log.action == AuditAction.CONDOMINIUMS_CHANGED
        assert log.user is client
        assert log.actor is admin
        assert log.old_value is None
        assert log.new_value is None
        assert log.added_condominiums == [{"id": str(added.id), "name": "Vale"}]
        assert log.removed_condominiums == [{"id": str(removed.id), "name": "Mirante"}]

    def test_other_actions_have_no_condominiums(self) -> None:
        log = UserAuditLog(
            action=AuditAction.ROLE_CHANGED,
            old_value=Role.OPERATOR.value,
            new_value=Role.CLIENT.value,
        )

        assert log.added_condominiums == []
        assert log.removed_condominiums == []


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


class FakeAuditLogRepository:
    def __init__(self) -> None:
        self.added: list[UserAuditLog] = []

    def add(self, log: UserAuditLog) -> None:
        self.added.append(log)


class FrozenNow:
    def now(self) -> datetime:
        return datetime(2026, 3, 2, 9, 0, tzinfo=UTC)


def build_invite_service(
    existing: dict[str, User] | None = None,
) -> tuple[
    InviteService,
    FakeUserRepository,
    FakeInviteRepository,
    FakeEmailSender,
    FakeAuditLogRepository,
]:
    users = FakeUserRepository(existing)
    invites = FakeInviteRepository()
    sender = FakeEmailSender()
    audit_logs = FakeAuditLogRepository()
    service = InviteService(
        session=FakeSession(),  # type: ignore[arg-type]
        users=users,  # type: ignore[arg-type]
        invites=invites,  # type: ignore[arg-type]
        audit_logs=audit_logs,  # type: ignore[arg-type]
        password_hasher=get_password_hasher(),
        email_sender=sender,
        clock=FrozenNow(),
        invite_link_duration=timedelta(hours=24),
        frontend_url="http://localhost:3000",
    )
    return service, users, invites, sender, audit_logs


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
    @pytest.mark.parametrize(
        ("existing_email", "details", "error"),
        [
            pytest.param(
                None, {"role": Role.ADMIN}, AdminRoleNotAllowedError, id="another-admin"
            ),
            pytest.param(
                None,
                {"is_lawyer": True},
                OabNumberRequiredError,
                id="us07-ca04-lawyer-without-oab",
            ),
            pytest.param(
                None,
                {"is_lawyer": False, "oab_number": "123456/SP"},
                OabNumberNotAllowedError,
                id="us07-ca04-oab-without-being-a-lawyer",
            ),
            pytest.param(
                "novo@example.com",
                {},
                EmailAlreadyInUseError,
                id="us07-ca03-email-already-registered",
            ),
        ],
    )
    def test_invalid_invite_is_refused_and_saves_nothing(
        self,
        existing_email: str | None,
        details: dict[str, Any],
        error: type[Exception],
    ) -> None:
        existing = {existing_email: build_admin()} if existing_email else None
        service, users, _, _, _ = build_invite_service(existing=existing)

        with pytest.raises(error):
            service.invite(build_admin(), build_details(**details))

        assert users.added == []

    def test_invite_stores_pending_user_and_sends_email(self) -> None:
        service, users, invites, sender, audit_logs = build_invite_service()
        admin = build_admin()

        user = service.invite(
            admin,
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

        assert len(audit_logs.added) == 1
        log = audit_logs.added[0]
        assert log.user is user
        assert log.actor is admin
        assert log.action == AuditAction.INVITED
        assert log.old_value is None
        assert log.new_value == Role.OPERATOR.value


class FailingEmailSender:
    def send(self, message: EmailMessage) -> None:
        raise ConnectionRefusedError("SMTP fora do ar")


class TestInviteEmailFailure:
    def test_invite_is_kept_and_the_failure_is_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """O convite já está gravado; um SMTP fora do ar não desfaz a criação."""
        service, users, invites, _, _ = build_invite_service()
        service._email_sender = FailingEmailSender()

        with caplog.at_level(logging.ERROR):
            invited = service.invite(build_admin(), build_details())

        assert users.added == [invited]
        assert len(invites.added) == 1
        assert "Falha ao enviar o e-mail de convite" in caplog.text


class TestInviteUserRequest:
    def test_oab_number_sent_as_null_is_no_oab(self) -> None:
        request = InviteUserRequest.model_validate(
            {
                "email": "novo@example.com",
                "name": "Novo",
                "role": "operator",
                "oab_number": None,
            }
        )

        assert request.oab_number is None
