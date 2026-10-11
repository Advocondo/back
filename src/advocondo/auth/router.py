from typing import Annotated

from fastapi import APIRouter, Depends, status

from advocondo.auth.dependencies import (
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
)
from advocondo.auth.service import AuthService, PasswordResetService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def log_in(
    request: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> LoginResponse:
    result = auth_service.log_in(
        request.email, request.password, remember_me=request.remember_me
    )
    return LoginResponse(
        access_token=result.token,
        expires_at=result.user_session.expires_at,
        user=AuthenticatedUser.model_validate(result.user_session.user),
    )


@router.get("/me")
def get_me(current_user: CurrentUser) -> AuthenticatedUser:
    return AuthenticatedUser.model_validate(current_user)


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
