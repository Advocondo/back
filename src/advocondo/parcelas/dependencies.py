from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.acordos.repository import AgreementRepository
from advocondo.common.clock import Clock, get_clock
from advocondo.db import get_session
from advocondo.notificacoes.dependencies import get_client_notification_service
from advocondo.notificacoes.service import ClientNotificationService
from advocondo.parcelas.repository import InstallmentRepository
from advocondo.parcelas.service import InstallmentService


def get_installment_service(
    session: Annotated[Session, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
    notifications: Annotated[
        ClientNotificationService, Depends(get_client_notification_service)
    ],
) -> InstallmentService:
    return InstallmentService(
        session=session,
        installments=InstallmentRepository(session),
        agreements=AgreementRepository(session),
        clock=clock,
        notifications=notifications,
    )
