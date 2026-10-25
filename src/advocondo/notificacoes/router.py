import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from advocondo.auth.dependencies import CurrentUser
from advocondo.notificacoes.dependencies import get_notification_service
from advocondo.notificacoes.schemas import (
    NotificationListResponse,
    NotificationResponse,
)
from advocondo.notificacoes.service import NotificationService

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

router = APIRouter(prefix="/notifications", tags=["notifications"])

NotificationServiceDependency = Annotated[
    NotificationService, Depends(get_notification_service)
]


@router.get("")
def list_own_notifications(
    current_user: CurrentUser,
    notification_service: NotificationServiceDependency,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NotificationListResponse:
    page = notification_service.list_own(current_user, limit, offset)
    return NotificationListResponse(
        unread_count=page.unread_count,
        notifications=[
            NotificationResponse.from_notification(item) for item in page.notifications
        ],
    )


@router.post("/{notification_id}/read")
def mark_notification_as_read(
    notification_id: uuid.UUID,
    current_user: CurrentUser,
    notification_service: NotificationServiceDependency,
) -> NotificationResponse:
    notification = notification_service.mark_as_read(current_user, notification_id)
    return NotificationResponse.from_notification(notification)


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_notifications_as_read(
    current_user: CurrentUser,
    notification_service: NotificationServiceDependency,
) -> None:
    notification_service.mark_all_as_read(current_user)
