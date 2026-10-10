"""Rules the database enforces on users, whatever code writes to it."""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from advocondo.users.models import Role, User, UserStatus


def build_user(**overrides: Any) -> User:
    fields: dict[str, Any] = {
        "email": "ana@example.com",
        "name": "Ana Souza",
        "role": Role.OPERATOR,
        "status": UserStatus.ACTIVE,
        "password_hash": "hash",
    }
    return User(**(fields | overrides))


def test_new_user_starts_pending_with_generated_id_and_timestamps(
    db_session: Session,
) -> None:
    user = User(email="ana@example.com", name="Ana Souza", role=Role.OPERATOR)

    db_session.add(user)
    db_session.flush()

    assert user.status == UserStatus.PENDING
    assert user.id is not None
    assert user.created_at is not None
    assert user.updated_at is not None


def test_email_is_unique(db_session: Session) -> None:
    db_session.add(build_user(email="ana@example.com"))
    db_session.flush()

    db_session.add(build_user(email="ana@example.com", name="Outra Ana"))

    with pytest.raises(IntegrityError, match="uq_users_email"):
        db_session.flush()


def test_email_must_be_stored_lowercase(db_session: Session) -> None:
    db_session.add(build_user(email="Ana@Example.com"))

    with pytest.raises(IntegrityError, match="ck_users_email_is_lowercase"):
        db_session.flush()


def test_active_user_must_have_a_password(db_session: Session) -> None:
    db_session.add(build_user(status=UserStatus.ACTIVE, password_hash=None))

    with pytest.raises(IntegrityError, match="ck_users_active_user_has_password"):
        db_session.flush()


@pytest.mark.parametrize(
    "status",
    [
        pytest.param(UserStatus.PENDING, id="pending-invite"),
        pytest.param(UserStatus.INACTIVE, id="inactive"),
    ],
)
def test_user_that_is_not_active_may_have_no_password(
    db_session: Session, status: UserStatus
) -> None:
    db_session.add(build_user(status=status, password_hash=None))
    db_session.flush()

    assert db_session.scalar(select(User.status)) == status
