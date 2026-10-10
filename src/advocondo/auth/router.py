from typing import Annotated

from fastapi import APIRouter, Depends

from advocondo.auth.dependencies import CurrentUser, get_auth_service
from advocondo.auth.schemas import AuthenticatedUser, LoginRequest, LoginResponse
from advocondo.auth.service import AuthService

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
