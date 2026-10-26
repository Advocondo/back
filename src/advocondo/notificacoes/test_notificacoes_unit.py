import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from advocondo.notificacoes.models import ClientNotificationEvent, Notification
from advocondo.notificacoes.overdue import recipients
from advocondo.notificacoes.service import ClientNotificationService
from advocondo.users.models import Role, User, UserStatus
from tests.support.clock import FrozenClock
from tests.support.email import Outbox

NOW = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)


def make_user(
    role: Role = Role.OPERATOR, status: UserStatus = UserStatus.ACTIVE
) -> User:
    return User(id=uuid.uuid4(), role=role, status=status)


class TestRecipients:
    def test_responsible_lawyer_and_administrators_are_notified(self) -> None:
        """US30-CA01"""
        lawyer = make_user()
        admins = [make_user(Role.ADMIN), make_user(Role.ADMIN)]

        assert recipients(lawyer, admins) == [*admins, lawyer]

    def test_only_administrators_without_a_responsible_lawyer(self) -> None:
        admins = [make_user(Role.ADMIN)]

        assert recipients(None, admins) == admins

    @pytest.mark.parametrize(
        "status",
        [
            pytest.param(UserStatus.INACTIVE, id="inactive"),
            pytest.param(UserStatus.PENDING, id="pending"),
        ],
    )
    def test_lawyer_who_is_not_active_is_not_notified(self, status: UserStatus) -> None:
        admins = [make_user(Role.ADMIN)]

        assert recipients(make_user(status=status), admins) == admins

    def test_administrator_who_is_the_responsible_lawyer_is_notified_once(
        self,
    ) -> None:
        admin_and_lawyer = make_user(Role.ADMIN)

        assert recipients(admin_and_lawyer, [admin_and_lawyer]) == [admin_and_lawyer]


class TestMarkAsRead:
    def test_keeps_the_date_of_the_first_reading(self) -> None:
        notification = Notification(created_at=NOW)

        notification.mark_as_read(NOW)
        notification.mark_as_read(NOW + timedelta(days=1))

        assert notification.read_at == NOW
        assert notification.is_read


class FailingLogRepository:
    """Um Cliente vinculado; gravar o registro do envio falha."""

    def __init__(self, client: User) -> None:
        self.client = client

    def list_active_clients(self, condominium_id: uuid.UUID) -> list[tuple[User, str]]:
        return [(self.client, "Residencial Mirante")]

    def save(self, notification: object) -> None:
        raise RuntimeError("banco fora do ar")


class RecordingSession:
    def __init__(self) -> None:
        self.rolled_back = False

    def commit(self) -> None:
        raise AssertionError("nada deve ser gravado")

    def rollback(self) -> None:
        self.rolled_back = True


class TestClientNotificationLogFailure:
    def test_failure_to_log_the_send_is_reported_without_raising(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """US40-CA03: o e-mail já saiu; a falha do registro não desfaz a operação
        que gerou o aviso, mas fica no log da aplicação."""
        client = User(id=uuid.uuid4(), name="Síndico", email="sindico@example.com")
        session = RecordingSession()
        outbox = Outbox()
        service = ClientNotificationService(
            session,  # type: ignore[arg-type]
            FailingLogRepository(client),  # type: ignore[arg-type]
            outbox,
            FrozenClock(),
            "https://app.example.com",
        )

        with caplog.at_level(logging.ERROR):
            service.send_condominium_update(
                uuid.uuid4(),
                ClientNotificationEvent.AGREEMENT_CREATED,
                "Um novo acordo foi registrado para este condomínio.",
            )

        assert [message.to for message in outbox.messages] == ["sindico@example.com"]
        assert session.rolled_back
        assert "Falha ao registrar notificação enviada" in caplog.text
