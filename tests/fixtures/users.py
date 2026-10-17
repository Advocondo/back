from typing import Protocol

import pytest
from sqlalchemy.orm import Session

from advocondo.common.passwords import get_password_hasher
from advocondo.users.models import Role, User, UserStatus

DEFAULT_PASSWORD = "senha-correta-123"  # gitleaks:allow (test-only password)


class CreateUser(Protocol):
    def __call__(
        self,
        *,
        email: str = ...,
        name: str = ...,
        role: Role = ...,
        status: UserStatus = ...,
        password: str | None = ...,
    ) -> User: ...


@pytest.fixture
def create_user(db_session: Session) -> CreateUser:
    def create(
        *,
        email: str = "ana@example.com",
        name: str = "Ana Souza",
        role: Role = Role.OPERATOR,
        status: UserStatus = UserStatus.ACTIVE,
        password: str | None = DEFAULT_PASSWORD,
    ) -> User:
        user = User(
            email=email,
            name=name,
            role=role,
            status=status,
            password_hash=get_password_hasher().hash(password) if password else None,
        )
        db_session.add(user)
        db_session.flush()
        return user

    return create
