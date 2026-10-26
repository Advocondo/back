from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from advocondo.common.clock import Clock, get_clock
from advocondo.common.storage import FileStorage, get_file_storage
from advocondo.db import get_session
from advocondo.notificacoes.dependencies import get_client_notification_service
from advocondo.notificacoes.service import ClientNotificationService
from advocondo.painel_cliente.monthly_report_repository import (
    CondominiumMonthlyReportRepository,
)
from advocondo.painel_cliente.monthly_report_service import (
    CondominiumMonthlyReportService,
)


def get_monthly_report_service(
    session: Annotated[Session, Depends(get_session)],
    notifications: Annotated[
        ClientNotificationService, Depends(get_client_notification_service)
    ],
    storage: Annotated[FileStorage, Depends(get_file_storage)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> CondominiumMonthlyReportService:
    return CondominiumMonthlyReportService(
        session,
        CondominiumMonthlyReportRepository(session),
        notifications,
        storage,
        clock,
    )
