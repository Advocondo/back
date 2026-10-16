import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from advocondo.auth.dependencies import CurrentSession
from advocondo.users.dependencies import (
    CurrentAdmin,
    get_invite_service,
    get_profile_service,
    get_user_management_service,
    get_user_service,
    require_setup_token,
)
from advocondo.users.schemas import (
    AcceptInviteRequest,
    FirstAdminRequest,
    InviteUserRequest,
    ProfileUpdateRequest,
    UserResponse,
    UserStatusUpdateRequest,
)
from advocondo.users.service import (
    InviteDetails,
    InviteService,
    ProfileChanges,
    ProfileService,
    UserManagementService,
    UserService,
)

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


@router.post(
    "/users/invites",
    status_code=status.HTTP_201_CREATED,
    tags=["users"],
)
def invite_user(
    request: InviteUserRequest,
    current_admin: CurrentAdmin,
    invite_service: Annotated[InviteService, Depends(get_invite_service)],
) -> UserResponse:
    user = invite_service.invite(
        current_admin,
        InviteDetails(
            email=request.email,
            name=request.name,
            role=request.role,
            is_lawyer=request.is_lawyer,
            oab_number=request.oab_number,
        ),
    )
    return UserResponse.model_validate(user)


@router.post("/users/invites/accept", tags=["users"])
def accept_invite(
    request: AcceptInviteRequest,
    invite_service: Annotated[InviteService, Depends(get_invite_service)],
) -> UserResponse:
    user = invite_service.accept_invite(request.token, request.password)
    return UserResponse.model_validate(user)


@router.patch("/users/{user_id}/status", tags=["users"])
def change_user_status(
    user_id: uuid.UUID,
    request: UserStatusUpdateRequest,
    current_admin: CurrentAdmin,
    user_management: Annotated[
        UserManagementService, Depends(get_user_management_service)
    ],
) -> UserResponse:
    user = user_management.change_status(current_admin, user_id, request.status)
    return UserResponse.model_validate(user)
