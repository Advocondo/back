import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, status

from advocondo.auth.dependencies import (
    CurrentSession,
    CurrentUser,
    get_auth_service,
    get_password_reset_service,
)
from advocondo.auth.schemas import (
    AuthenticatedUser,
    LoginRequest,
    LoginResponse,
    PasswordResetConfirmation,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    SessionResponse,
)
from advocondo.auth.service import AuthService, PasswordResetService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def log_in(
    request: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    user_agent: Annotated[str | None, Header()] = None,
) -> LoginResponse:
    result = auth_service.log_in(
        request.email,
        request.password,
        remember_me=request.remember_me,
        user_agent=user_agent,
    )
    return LoginResponse(
        access_token=result.token,
        expires_at=result.user_session.expires_at,
        user=AuthenticatedUser.model_validate(result.user_session.user),
    )


@router.get("/me")
def get_me(current_user: CurrentUser) -> AuthenticatedUser:
    return AuthenticatedUser.model_validate(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def log_out(
    current_session: CurrentSession,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    auth_service.log_out(current_session)


@router.get("/sessions")
def list_sessions(
    current_session: CurrentSession,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> list[SessionResponse]:
    return [
        SessionResponse(
            id=item.id,
            user_agent=item.user_agent,
            created_at=item.created_at,
            expires_at=item.expires_at,
            is_current=item.id == current_session.id,
        )
        for item in auth_service.list_sessions(current_session.user)
    ]


# Antes de /sessions/{session_id}, para "others" não ser lido como um id.
@router.delete("/sessions/others", status_code=status.HTTP_204_NO_CONTENT)
def end_other_sessions(
    current_session: CurrentSession,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    auth_service.end_other_sessions(current_session)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def end_session(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    auth_service.end_session(current_user, session_id)


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT)
def end_all_sessions(
    current_user: CurrentUser,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    auth_service.end_all_sessions(current_user)


@router.post("/password-reset", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    request: PasswordResetRequest,
    password_reset_service: Annotated[
        PasswordResetService, Depends(get_password_reset_service)
    ],
) -> PasswordResetRequestResponse:
    password_reset_service.request_reset(request.email)
    return PasswordResetRequestResponse()


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    request: PasswordResetConfirmation,
    password_reset_service: Annotated[
        PasswordResetService, Depends(get_password_reset_service)
    ],
) -> None:
    password_reset_service.reset_password(request.token, request.new_password)
