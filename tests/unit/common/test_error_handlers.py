import pytest

from advocondo.common.error_handlers import status_for
from advocondo.common.errors import (
    AppError,
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)


class ExpiredLinkError(AuthenticationError):
    pass


@pytest.mark.parametrize(
    ("error", "status"),
    [
        pytest.param(ExpiredLinkError(), 401, id="authentication-subclass"),
        pytest.param(PermissionDeniedError(), 403, id="permission-denied"),
        pytest.param(NotFoundError(), 404, id="not-found"),
        pytest.param(ConflictError(), 409, id="conflict"),
        pytest.param(BusinessRuleError(), 422, id="business-rule"),
        pytest.param(AppError(), 400, id="unmapped"),
    ],
)
def test_each_error_maps_to_its_http_status(error: AppError, status: int) -> None:
    assert status_for(error) == status


def test_custom_message_replaces_the_default() -> None:
    assert NotFoundError("Acordo não encontrado.").message == "Acordo não encontrado."
