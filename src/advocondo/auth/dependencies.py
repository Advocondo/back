from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from advocondo.auth.errors import InvalidSessionError
from advocondo.auth.repository import UserSessionRepository
from advocondo.auth.service import AuthService, SessionDurations
from advocondo.common.clock import Clock, get_clock
from advocondo.common.passwords import PasswordHasher, get_password_hasher
from advocondo.config import Settings, get_settings
from advocondo.db import get_session
from advocondo.users.models import User
from advocondo.users.repository import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(
    session: Annotated[Session, Depends(get_session)],
    password_hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    clock: Annotated[Clock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthService:
    return AuthService(
        session=session,
        users=UserRepository(session),
        user_sessions=UserSessionRepository(session),
        password_hasher=password_hasher,
        clock=clock,
        session_durations=SessionDurations(
            default=settings.session_duration,
            remembered=settings.remembered_session_duration,
        ),
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    if credentials is None:
        raise InvalidSessionError()
    return auth_service.authenticate(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]
