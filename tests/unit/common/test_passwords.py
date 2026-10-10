import pytest

from advocondo.common.passwords import PasswordHasher

hasher = PasswordHasher()
PASSWORD_HASH = hasher.hash("senha-correta")


def test_hash_does_not_contain_the_password() -> None:
    assert "senha-correta" not in PASSWORD_HASH


@pytest.mark.parametrize(
    ("password", "expected"),
    [
        pytest.param("senha-correta", True, id="right-password"),
        pytest.param("senha-errada", False, id="wrong-password"),
        pytest.param("", False, id="empty-password"),
    ],
)
def test_verify_accepts_only_the_hashed_password(password: str, expected: bool) -> None:
    assert hasher.verify(PASSWORD_HASH, password) is expected
