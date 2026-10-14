import secrets
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from advocondo.auth.repository import UserSessionRepository
from advocondo.common.passwords import PasswordHasher, get_password_hasher
from advocondo.config import Settings, get_settings
from advocondo.db import get_session
from advocondo.users.errors import InvalidSetupTokenError, SetupDisabledError
from advocondo.users.repository import UserRepository
from advocondo.users.service import ProfileService, UserService


def get_user_service(
    session: Annotated[Session, Depends(get_session)],
    password_hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
) -> UserService:
    return UserService(session, UserRepository(session), password_hasher)


def get_profile_service(
    session: Annotated[Session, Depends(get_session)],
    password_hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
) -> ProfileService:
    return ProfileService(
        session=session,
        users=UserRepository(session),
        user_sessions=UserSessionRepository(session),
        password_hasher=password_hasher,
    )


def require_setup_token(
    settings: Annotated[Settings, Depends(get_settings)],
    setup_token: Annotated[str | None, Header(alias="X-Setup-Token")] = None,
) -> None:
    if not settings.setup_token:
        raise SetupDisabledError()
    # Constant-time comparison, so the response time does not leak the token.
    if setup_token is None or not secrets.compare_digest(
        setup_token.encode(), settings.setup_token.encode()
    ):
        raise InvalidSetupTokenError()
