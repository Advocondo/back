import pytest

from advocondo.auth.dependencies import require_office_staff
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
