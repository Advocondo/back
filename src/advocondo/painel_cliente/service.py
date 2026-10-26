import uuid
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from advocondo.acordos.errors import AgreementNotFoundError
from advocondo.acordos.models import Agreement
from advocondo.devedores.errors import DebtorNotFoundError
from advocondo.painel_cliente.repository import ClientPanelRepository
from advocondo.painel_cliente.schemas import (
    AgreementStanding,
    AgreementSummary,
    ClientInstallment,
    DebtorPaymentHistory,
    MonthStanding,
    PaymentHistoryMonth,
)
from advocondo.parcelas.models import Installment
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
        debtor_id=agreement.debtor.id,
        debtor_name=agreement.debtor.name,
        debtor_unit=agreement.debtor.unit,
        status=AgreementStanding.OVERDUE if overdue else AgreementStanding.ON_TIME,
        overdue_installments=overdue,
        next_due_date=min(upcoming, default=None),
    )


def summarize_months(
    collected: Iterable[Installment],
    cancelled: Iterable[Installment],
    today: date,
) -> list[PaymentHistoryMonth]:
    """Groups the installments by competência, the month of the due date (US38),
    oldest first. `collected` are the installments of active agreements;
    `cancelled` are those of cancelled agreements, which only add what was paid on
    them, since their unpaid part is no longer charged (US20).

    A month is overdue if any collected unpaid installment in it is overdue, open
    if any is still unpaid, and paid otherwise."""
    paid: dict[str, Decimal] = {}
    open_amount: dict[str, Decimal] = {}
    statuses: dict[str, set[InstallmentStatus]] = {}

    def month_of(installment: Installment) -> str:
        return installment.due_date.strftime("%Y-%m")

    for installment in collected:
        month = month_of(installment)
        paid[month] = paid.get(month, Decimal(0)) + installment.paid_amount
        open_amount[month] = (
            open_amount.get(month, Decimal(0)) + installment.remaining_amount
        )
        statuses.setdefault(month, set()).add(installment.status_on(today))
    for installment in cancelled:
        if installment.paid_amount > 0:
            month = month_of(installment)
            paid[month] = paid.get(month, Decimal(0)) + installment.paid_amount

    months = []
    for month in sorted(paid):
        month_statuses = statuses.get(month, set())
        if InstallmentStatus.OVERDUE in month_statuses:
            standing = MonthStanding.OVERDUE
        elif InstallmentStatus.OPEN in month_statuses:
            standing = MonthStanding.OPEN
        else:
            standing = MonthStanding.PAID
        months.append(
            PaymentHistoryMonth(
                month=month,
                paid_amount=paid[month],
                open_amount=open_amount.get(month, Decimal(0)),
                status=standing,
            )
        )
    return months


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

    def debtor_history(
        self, user_id: uuid.UUID, debtor_id: uuid.UUID, today: date
    ) -> DebtorPaymentHistory:
        """Paid and open totals of a resident, by competência (US38). Debtors of
        other condominiums answer as unknown. Cancelled agreements only add what was
        paid on them, for the accountability the story asks for."""
        debtor = self._agreements.get_debtor_of_client(user_id, debtor_id)
        if debtor is None:
            raise DebtorNotFoundError()
        agreements = self._agreements.list_agreements_of_debtor(user_id, debtor_id)
        return DebtorPaymentHistory(
            debtor_name=debtor.name,
            debtor_unit=debtor.unit,
            months=summarize_months(
                (
                    item
                    for agreement in agreements
                    if not agreement.is_cancelled
                    for item in agreement.installments
                ),
                (
                    item
                    for agreement in agreements
                    if agreement.is_cancelled
                    for item in agreement.installments
                ),
                today,
            ),
        )
