import pytest

from advocondo.users.models import Role, User, UserStatus


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
