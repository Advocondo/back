from typing import Annotated

from fastapi import APIRouter, Depends, status

from advocondo.users.dependencies import get_user_service, require_setup_token
from advocondo.users.schemas import FirstAdminRequest, UserResponse
from advocondo.users.service import UserService

router = APIRouter(tags=["setup"])


@router.post(
    "/setup",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_setup_token)],
)
def create_first_admin(
    request: FirstAdminRequest,
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    user = user_service.create_first_admin(
        request.email, request.name, request.password
    )
    return UserResponse.model_validate(user)
