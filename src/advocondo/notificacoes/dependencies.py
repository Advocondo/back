from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.common.clock import Clock, get_clock
from advocondo.common.email import EmailSender, get_email_sender
from advocondo.config import Settings, get_settings
from advocondo.db import get_session
from advocondo.notificacoes.repository import ClientNotificationRepository
from advocondo.notificacoes.service import ClientNotificationService


def get_client_notification_service(
    session: Annotated[Session, Depends(get_session)],
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
    clock: Annotated[Clock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClientNotificationService:
    return ClientNotificationService(
        session=session,
        notifications=ClientNotificationRepository(session),
        email_sender=email_sender,
        clock=clock,
        frontend_url=settings.frontend_url,
    )
