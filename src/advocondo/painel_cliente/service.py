import uuid
from datetime import date

from advocondo.acordos.errors import AgreementNotFoundError
from advocondo.acordos.models import Agreement
from advocondo.painel_cliente.repository import ClientPanelRepository
from advocondo.painel_cliente.schemas import (
    AgreementStanding,
    AgreementSummary,
    ClientInstallment,
)
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

    def list_unpaid_installments(
        self, user_id: uuid.UUID, agreement_id: uuid.UUID, today: date
    ) -> list[ClientInstallment]:
        """Unpaid installments of an agreement the Client sees in the panel (#89).
        Agreements of other condominiums and cancelled ones answer as unknown, so
        the Client cannot tell whether they exist."""
        agreement = self._agreements.get_agreement_of_client(user_id, agreement_id)
        if agreement is None:
            raise AgreementNotFoundError()
        return [
            ClientInstallment(
                number=installment.number,
                due_date=installment.due_date,
                amount=installment.amount,
                remaining_amount=installment.remaining_amount,
                status=installment.status_on(today),
            )
            for installment in agreement.unpaid_installments
        ]
