from typing import Annotated

from fastapi import APIRouter, Depends, status

from advocondo.auth.dependencies import CurrentSession
from advocondo.users.dependencies import (
    get_profile_service,
    get_user_service,
    require_setup_token,
)
from advocondo.users.schemas import (
    FirstAdminRequest,
    ProfileUpdateRequest,
    UserResponse,
)
from advocondo.users.service import ProfileChanges, ProfileService, UserService

router = APIRouter()


@router.post(
    "/setup",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_setup_token)],
    tags=["setup"],
)
def create_first_admin(
    request: FirstAdminRequest,
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    user = user_service.create_first_admin(
        request.email, request.name, request.password
    )
    return UserResponse.model_validate(user)


@router.patch("/users/me", tags=["users"])
def update_profile(
    request: ProfileUpdateRequest,
    current_session: CurrentSession,
    profile_service: Annotated[ProfileService, Depends(get_profile_service)],
) -> UserResponse:
    user = profile_service.update_profile(
        current_session,
        ProfileChanges(
            name=request.name,
            email=request.email,
            new_password=request.new_password,
            current_password=request.current_password,
        ),
    )
    return UserResponse.model_validate(user)
