from collections.abc import Callable
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


@pytest.mark.parametrize(
    ("require", "role", "allowed"),
    [
        pytest.param(require_office_staff, Role.ADMIN, True, id="office-admin"),
        pytest.param(require_office_staff, Role.OPERATOR, True, id="office-operator"),
        pytest.param(require_office_staff, Role.CLIENT, False, id="office-client"),
        pytest.param(require_client, Role.CLIENT, True, id="client-panel-client"),
        pytest.param(require_client, Role.ADMIN, False, id="client-panel-admin"),
        pytest.param(require_client, Role.OPERATOR, False, id="client-panel-operator"),
    ],
)
def test_only_the_allowed_roles_pass(
    require: Callable[[User], User], role: Role, allowed: bool
) -> None:
    """Rotas do escritório são da Equipe Operacional e do Administrador; o painel
    do Cliente (EP06), só do Cliente."""
    user = make_user(role)

    if allowed:
        assert require(user) is user
    else:
        with pytest.raises(PermissionDeniedError):
            require(user)


@pytest.mark.parametrize(
    ("request_window", "retention"),
    [
        pytest.param(
            timedelta(minutes=60),
            MIN_EXPIRED_RESET_LINK_RETENTION,
            id="short-window-keeps-a-day",
        ),
        pytest.param(timedelta(hours=24), timedelta(hours=24), id="exactly-a-day"),
        pytest.param(
            timedelta(hours=48),
            timedelta(hours=48),
            id="longer-window-keeps-the-window",
        ),
    ],
)
def test_expired_reset_links_are_kept_for_the_request_window(
    request_window: timedelta, retention: timedelta
) -> None:
    assert MIN_EXPIRED_RESET_LINK_RETENTION == timedelta(hours=24)
    assert expired_reset_link_retention(request_window) == retention
