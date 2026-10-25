from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.acordos.lawyer_assignment import LawyerAssignmentService
from advocondo.acordos.repository import AgreementRepository
from advocondo.acordos.service import AgreementService
from advocondo.common.clock import Clock, get_clock
from advocondo.condominios.repository import CondominiumRepository
from advocondo.db import get_session
from advocondo.devedores.repository import DebtorRepository
from advocondo.notificacoes.dependencies import get_client_notification_service
from advocondo.notificacoes.service import ClientNotificationService
from advocondo.users.repository import UserRepository


def get_agreement_service(
    session: Annotated[Session, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
    notifications: Annotated[
        ClientNotificationService, Depends(get_client_notification_service)
    ],
) -> AgreementService:
    return AgreementService(
        session=session,
        agreements=AgreementRepository(session),
        condominiums=CondominiumRepository(session),
        debtors=DebtorRepository(session),
        clock=clock,
        notifications=notifications,
    )


def get_lawyer_assignment_service(
    session: Annotated[Session, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> LawyerAssignmentService:
    return LawyerAssignmentService(
        session, AgreementRepository(session), UserRepository(session), clock
    )
