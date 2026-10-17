from collections.abc import Callable, Iterator

import pytest
from sqlalchemy.orm import Session

from advocondo.auth.models import UserSession
from advocondo.common.clock import get_clock
from advocondo.common.tokens import generate_opaque_token, hash_token
from advocondo.config import get_settings
from advocondo.main import app
from advocondo.users.models import User
from tests.support.clock import FrozenClock

AuthenticateAs = Callable[[User], dict[str, str]]


@pytest.fixture
def clock() -> Iterator[FrozenClock]:
    frozen_clock = FrozenClock()
    app.dependency_overrides[get_clock] = lambda: frozen_clock
    try:
        yield frozen_clock
    finally:
        app.dependency_overrides.pop(get_clock, None)


@pytest.fixture
def authenticate_as(db_session: Session, clock: FrozenClock) -> AuthenticateAs:
    """Logs the user in without going through POST /auth/login; returns the headers."""

    def authenticate(user: User) -> dict[str, str]:
        token = generate_opaque_token()
        db_session.add(
            UserSession(
                user=user,
                token_hash=hash_token(token),
                expires_at=clock.now() + get_settings().session_duration,
            )
        )
        db_session.flush()
        return {"Authorization": f"Bearer {token}"}

    return authenticate
