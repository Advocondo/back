import uuid
from datetime import date

from advocondo.acordos.models import Agreement
from advocondo.common.errors import NotFoundError
from advocondo.painel_cliente.report_pdf import render_condominium_report
from advocondo.painel_cliente.repository import ClientPanelRepository
from advocondo.painel_cliente.schemas import AgreementStanding, AgreementSummary
from advocondo.parcelas.status import InstallmentStatus


def summarize_agreement(agreement: Agreement, today: date) -> AgreementSummary:
    statuses = [
        (installment, installment.status_on(today))
        for installment in agreement.installments
    ]
    overdue = sum(1 for _, status in statuses if status == InstallmentStatus.OVERDUE)
    upcoming = [
        installment.due_date
        for installment, status in statuses
        if status == InstallmentStatus.OPEN
    ]
    return AgreementSummary(
        id=agreement.id,
        condominium_name=agreement.condominium.name,
        debtor_name=agreement.debtor.name,
        debtor_unit=agreement.debtor.unit,
        status=AgreementStanding.OVERDUE if overdue else AgreementStanding.ON_TIME,
        overdue_installments=overdue,
        next_due_date=min(upcoming, default=None),
    )


class ClientPanelService:
    def __init__(self, agreements: ClientPanelRepository) -> None:
        self._agreements = agreements

    def list_agreements(
        self, user_id: uuid.UUID, today: date
    ) -> list[AgreementSummary]:
        """Overdue agreements first. Within each group the repository's order (by
        condominium and debtor name) is kept, because `sorted` is stable."""
        summaries = [
            summarize_agreement(agreement, today)
            for agreement in self._agreements.list_agreements_of_client(user_id)
        ]
        return sorted(
            summaries, key=lambda item: item.status != AgreementStanding.OVERDUE
        )

    def condominium_report(
        self,
        user_id: uuid.UUID,
        condominium_id: uuid.UUID,
        client_name: str,
        today: date,
    ) -> bytes:
        condominium = self._agreements.get_linked_condominium(user_id, condominium_id)
        if condominium is None:
            raise CondominiumReportNotFoundError()
        agreements = self._agreements.list_active_agreements_for_condominium(
            user_id, condominium_id
        )
        return render_condominium_report(
            client_name, condominium, list(agreements), today
        )


class CondominiumReportNotFoundError(NotFoundError):
    message = "Relatório não encontrado."
