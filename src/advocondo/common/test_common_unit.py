from datetime import UTC

import pytest

from advocondo.common.clock import get_clock
from advocondo.common.error_handlers import status_for
from advocondo.common.errors import (
    AppError,
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from advocondo.common.passwords import PasswordHasher
from advocondo.common.tokens import generate_opaque_token, hash_token


class ExpiredLinkError(AuthenticationError):
    pass


hasher = PasswordHasher()


PASSWORD_HASH = hasher.hash("senha-correta")


class TestClock:
    def test_system_clock_returns_an_aware_utc_datetime(self) -> None:
        assert get_clock().now().tzinfo == UTC


class TestErrorHandlers:
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
    def test_each_error_maps_to_its_http_status(
        self, error: AppError, status: int
    ) -> None:
        assert status_for(error) == status

    def test_custom_message_replaces_the_default(self) -> None:
        assert (
            NotFoundError("Acordo não encontrado.").message == "Acordo não encontrado."
        )


class TestPasswords:
    def test_hash_does_not_contain_the_password(self) -> None:
        assert "senha-correta" not in PASSWORD_HASH

    @pytest.mark.parametrize(
        ("password", "expected"),
        [
            pytest.param("senha-correta", True, id="right-password"),
            pytest.param("senha-errada", False, id="wrong-password"),
            pytest.param("", False, id="empty-password"),
        ],
    )
    def test_verify_accepts_only_the_hashed_password(
        self, password: str, expected: bool
    ) -> None:
        assert hasher.verify(PASSWORD_HASH, password) is expected


class TestTokens:
    def test_generated_tokens_are_unique(self) -> None:
        assert generate_opaque_token() != generate_opaque_token()

    def test_hash_is_stable_and_does_not_contain_the_token(self) -> None:
        token = generate_opaque_token()

        assert hash_token(token) == hash_token(token)
        assert token not in hash_token(token)
