import uuid
from datetime import UTC, datetime, timedelta

import pytest

from advocondo.notificacoes.models import Notification
from advocondo.notificacoes.overdue import recipients
from advocondo.users.models import Role, User, UserStatus

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
