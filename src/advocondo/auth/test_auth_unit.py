from datetime import timedelta

import pytest

from advocondo.auth.cleanup import (
    MIN_EXPIRED_RESET_LINK_RETENTION,
    expired_reset_link_retention,
)
from advocondo.auth.dependencies import require_client, require_office_staff
from advocondo.common.errors import PermissionDeniedError
from advocondo.users.models import Role, User, UserStatus


def make_user(role: Role) -> User:
    return User(
        email="ana@example.com", name="Ana", role=role, status=UserStatus.ACTIVE
    )


class TestRequireOfficeStaff:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.OPERATOR])
    def test_office_staff_is_allowed(self, role: Role) -> None:
        user = make_user(role)

        assert require_office_staff(user) is user

    def test_client_is_refused(self) -> None:
        with pytest.raises(PermissionDeniedError):
            require_office_staff(make_user(Role.CLIENT))


class TestRequireClient:
    def test_client_is_allowed(self) -> None:
        user = make_user(Role.CLIENT)

        assert require_client(user) is user

    @pytest.mark.parametrize("role", [Role.ADMIN, Role.OPERATOR])
    def test_office_staff_is_refused(self, role: Role) -> None:
        with pytest.raises(PermissionDeniedError):
            require_client(make_user(role))


class TestExpiredResetLinkRetention:
    def test_a_short_request_window_keeps_links_for_a_day(self) -> None:
        retention = expired_reset_link_retention(timedelta(minutes=60))

        assert retention == MIN_EXPIRED_RESET_LINK_RETENTION == timedelta(hours=24)

    def test_a_request_window_longer_than_a_day_keeps_links_for_the_window(
        self,
    ) -> None:
        assert expired_reset_link_retention(timedelta(hours=48)) == timedelta(hours=48)
