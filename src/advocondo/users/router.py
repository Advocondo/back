import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from advocondo.auth.dependencies import CurrentSession
from advocondo.users.dependencies import (
    CurrentAdmin,
    get_audit_service,
    get_invite_service,
    get_profile_service,
    get_user_management_service,
    get_user_service,
    require_setup_token,
    require_staff,
)
from advocondo.users.schemas import (
    AcceptInviteRequest,
    FirstAdminRequest,
    InviteUserRequest,
    LawyerResponse,
    ProfileUpdateRequest,
    UserAuditLogListResponse,
    UserAuditLogResponse,
    UserResponse,
    UserRoleUpdateRequest,
    UserStatusUpdateRequest,
)
from advocondo.users.service import (
    AuditService,
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


@router.get(
    "/users/lawyers",
    tags=["users"],
    dependencies=[Depends(require_staff)],
)
def list_lawyers(
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> list[LawyerResponse]:
    lawyers = user_service.list_responsible_lawyers()
    return [LawyerResponse.model_validate(lawyer) for lawyer in lawyers]
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


@router.patch("/users/{user_id}/role", tags=["users"])
def change_user_role(
    user_id: uuid.UUID,
    request: UserRoleUpdateRequest,
    current_admin: CurrentAdmin,
    user_management: Annotated[
        UserManagementService, Depends(get_user_management_service)
    ],
) -> UserResponse:
    user = user_management.change_role(current_admin, user_id, request.role)
    return UserResponse.model_validate(user)


@router.get("/users/{user_id}/history", tags=["users"])
def get_user_history(
    user_id: uuid.UUID,
    current_admin: CurrentAdmin,
    audit_service: Annotated[AuditService, Depends(get_audit_service)],
) -> UserAuditLogListResponse:
    logs = audit_service.list_user_history(user_id)
    return UserAuditLogListResponse(
        logs=[UserAuditLogResponse.model_validate(log) for log in logs]
    )
