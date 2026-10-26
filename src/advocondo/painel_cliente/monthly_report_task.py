"""Creates the previous month's condominium reports and emails linked Clients.

Run daily as a Coolify Scheduled Task; an existing report is reused and sent
notifications are not repeated, so reruns after a temporary failure are safe.
"""

from advocondo.common.clock import get_clock
from advocondo.common.email import build_email_sender
from advocondo.common.storage import build_file_storage
from advocondo.config import get_settings
from advocondo.db import get_sessionmaker
from advocondo.notificacoes.repository import ClientNotificationRepository
from advocondo.notificacoes.service import ClientNotificationService
from advocondo.painel_cliente.monthly_report_repository import (
    CondominiumMonthlyReportRepository,
)
from advocondo.painel_cliente.monthly_report_service import (
    CondominiumMonthlyReportService,
)


def main() -> None:
    settings = get_settings()
    with get_sessionmaker()() as session:
        notifications = ClientNotificationService(
            session,
            ClientNotificationRepository(session),
            build_email_sender(settings),
            get_clock(),
            settings.frontend_url,
        )
        service = CondominiumMonthlyReportService(
            session,
            CondominiumMonthlyReportRepository(session),
            notifications,
            build_file_storage(settings),
            get_clock(),
        )
        result = service.close_previous_month()
    print(
        f"{result.reports_created} relatórios gerados para "
        f"{result.month:02}/{result.year}."
    )


if __name__ == "__main__":
    main()
