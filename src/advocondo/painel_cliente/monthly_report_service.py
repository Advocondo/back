import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from advocondo.common.clock import Clock, today_in_brazil
from advocondo.common.errors import NotFoundError
from advocondo.common.pdf import PDF_CONTENT_TYPE
from advocondo.common.storage import FileStorage
from advocondo.notificacoes.models import ClientNotificationEvent
from advocondo.notificacoes.service import ClientNotificationService
from advocondo.painel_cliente.models import CondominiumMonthlyReport
from advocondo.painel_cliente.monthly_report_repository import (
    CondominiumMonthlyReportRepository,
)
from advocondo.painel_cliente.report_pdf import render_condominium_report


@dataclass(frozen=True)
class MonthlyReportRun:
    year: int
    month: int
    reports_created: int


class CondominiumMonthlyReportService:
    def __init__(
        self,
        session: Session,
        reports: CondominiumMonthlyReportRepository,
        notifications: ClientNotificationService,
        storage: FileStorage,
        clock: Clock,
    ) -> None:
        self._session = session
        self._reports = reports
        self._notifications = notifications
        self._storage = storage
        self._clock = clock

    def close_previous_month(self) -> MonthlyReportRun:
        now = self._clock.now()
        today = today_in_brazil(now)
        first_day = date(today.year, today.month, 1)
        period_end = first_day - timedelta(days=1)
        year, month = period_end.year, period_end.month
        period_label = f"{month:02}/{year}"
        message = (
            f"O relatório mensal referente a {period_label} está disponível "
            "no painel do cliente."
        )
        reports_created = 0

        for condominium in self._reports.list_condominiums_with_active_clients():
            report = self._reports.get(condominium.id, year, month)
            if report is None:
                content = render_condominium_report(
                    client_name="",
                    condominium=condominium,
                    agreements=list(
                        self._reports.list_active_agreements(condominium.id)
                    ),
                    today=period_end,
                    period_label=period_label,
                )
                report = CondominiumMonthlyReport(
                    id=uuid.uuid4(),
                    condominium_id=condominium.id,
                    year=year,
                    month=month,
                    generated_at=now,
                )
                key = f"condominiums/{condominium.id}/reports/{year}-{month:02}.pdf"
                self._storage.save(report, key, content, PDF_CONTENT_TYPE)
                self._reports.save(report)
                self._session.commit()
                reports_created += 1

            self._notifications.send_condominium_update(
                condominium.id,
                ClientNotificationEvent.MONTHLY_REPORT_READY,
                message,
                include_frontend_link=False,
                skip_already_sent=True,
            )

        return MonthlyReportRun(year, month, reports_created)

    def download_for_client(
        self,
        user_id: uuid.UUID,
        condominium_id: uuid.UUID,
        year: int,
        month: int,
    ) -> tuple[CondominiumMonthlyReport, bytes]:
        report = self._reports.get_for_client(user_id, condominium_id, year, month)
        if report is None:
            raise MonthlyReportNotFoundError()
        return report, self._storage.load(report)


class MonthlyReportNotFoundError(NotFoundError):
    message = "Relatório mensal não encontrado."
