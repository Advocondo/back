from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.common.clock import Clock, get_clock
from advocondo.db import get_session
from advocondo.notificacoes.repository import NotificationRepository
from advocondo.notificacoes.service import NotificationService


def get_notification_service(
    session: Annotated[Session, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> NotificationService:
    return NotificationService(session, NotificationRepository(session), clock)
