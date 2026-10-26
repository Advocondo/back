from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.condominios.repository import CondominiumRepository
from advocondo.condominios.service import CondominiumService
from advocondo.db import get_session
from advocondo.notificacoes.dependencies import get_client_notification_service
from advocondo.notificacoes.service import ClientNotificationService


def get_condominium_service(
    session: Annotated[Session, Depends(get_session)],
    notifications: Annotated[
        ClientNotificationService, Depends(get_client_notification_service)
    ],
) -> CondominiumService:
    return CondominiumService(session, CondominiumRepository(session), notifications)
