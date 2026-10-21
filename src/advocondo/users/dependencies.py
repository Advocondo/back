import secrets
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from advocondo.auth.dependencies import CurrentUser
from advocondo.auth.repository import UserSessionRepository
from advocondo.common.clock import Clock, get_clock
from advocondo.common.email import EmailSender, get_email_sender
from advocondo.common.errors import PermissionDeniedError
from advocondo.common.passwords import PasswordHasher, get_password_hasher
from advocondo.config import Settings, get_settings
from advocondo.db import get_session
from advocondo.users.errors import InvalidSetupTokenError, SetupDisabledError
from advocondo.users.models import Role, User
from advocondo.users.repository import (
    UserAuditLogRepository,
    UserInviteRepository,
    UserRepository,
)
from advocondo.users.service import (
    AuditService,
    InviteService,
    ProfileService,
    UserManagementService,
    UserService,
)


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


def get_invite_service(
    session: Annotated[Session, Depends(get_session)],
    password_hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
    clock: Annotated[Clock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> InviteService:
    return InviteService(
        session=session,
        users=UserRepository(session),
        invites=UserInviteRepository(session),
        audit_logs=UserAuditLogRepository(session),
        password_hasher=password_hasher,
        email_sender=email_sender,
        clock=clock,
        invite_link_duration=settings.invite_link_duration,
        frontend_url=settings.frontend_url,
    )


def get_user_management_service(
    session: Annotated[Session, Depends(get_session)],
) -> UserManagementService:
    return UserManagementService(
        session=session,
        users=UserRepository(session),
        audit_logs=UserAuditLogRepository(session),
    )


def get_audit_service(
    session: Annotated[Session, Depends(get_session)],
) -> AuditService:
    return AuditService(
        users=UserRepository(session),
        audit_logs=UserAuditLogRepository(session),
    )


def require_setup_token(
    settings: Annotated[Settings, Depends(get_settings)],
    setup_token: Annotated[str | None, Header(alias="X-Setup-Token")] = None,
) -> None:
    if not settings.setup_token:
        raise SetupDisabledError()
    if setup_token is None or not secrets.compare_digest(
        setup_token.encode(), settings.setup_token.encode()
    ):
        raise InvalidSetupTokenError()


def require_admin(current_user: CurrentUser) -> User:
    if current_user.role != Role.ADMIN:
        raise PermissionDeniedError()
    return current_user

CurrentAdmin = Annotated[User, Depends(require_admin)]
