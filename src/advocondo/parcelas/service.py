import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from advocondo.acordos.errors import AgreementCancelledError, AgreementNotFoundError
from advocondo.acordos.models import AgreementStatus
from advocondo.acordos.repository import AgreementRepository
from advocondo.parcelas.errors import (
    InstallmentAlreadyPaidError,
    InstallmentNotFoundError,
    InstallmentNotPaidError,
    NoOpenInstallmentAfterError,
    PaidInstallmentCannotBeEditedError,
    PaymentDateInTheFutureError,
)
from advocondo.parcelas.models import Installment
from advocondo.parcelas.plan import (
    absorb_difference,
    first_and_last_day_of_month,
    split_fee,
)
from advocondo.parcelas.repository import InstallmentFilters, InstallmentRepository
from advocondo.parcelas.schemas import InstallmentUpdateRequest


class InstallmentService:
    def __init__(
        self,
        session: Session,
        installments: InstallmentRepository,
        agreements: AgreementRepository,
    ) -> None:
        self._session = session
        self._installments = installments
        self._agreements = agreements

    def list_plan(self, agreement_id: uuid.UUID) -> Sequence[Installment]:
        """The installments of an agreement, in order."""
        if self._agreements.get(agreement_id) is None:
            raise AgreementNotFoundError()
        return self._installments.list_by_agreement(agreement_id)

    def list_due_in_month(
        self,
        year: int,
        month: int,
        filters: InstallmentFilters,
        today: date,
        limit: int,
        offset: int,
    ) -> Sequence[Installment]:
        """Parcelas que vencem no mês (US25-CA01), com os filtros opcionais
        (US25-CA02). `today` decide quais parcelas sem pagamento estão atrasadas."""
        first_day, last_day = first_and_last_day_of_month(year, month)
        return self._installments.search_due_between(
            first_day, last_day, filters, today, limit, offset
        )

    def record_payment(
        self, installment_id: uuid.UUID, payment_date: date, today: date
    ) -> Installment:
        """Dá baixa na parcela em aberto: ela passa a constar como paga (US26-CA01)."""
        installment = self._get_installment_for_update(installment_id)
        ensure_agreement_is_not_cancelled(installment)
        if installment.is_paid:
            raise InstallmentAlreadyPaidError()
        ensure_payment_date_is_not_in_the_future(payment_date, today)
        installment.payment_date = payment_date
        self._session.commit()
        return installment

    def correct_payment(
        self, installment_id: uuid.UUID, payment_date: date, today: date
    ) -> Installment:
        """Troca a data do pagamento de uma parcela já baixada (US26-CA02)."""
        installment = self._get_installment_for_update(installment_id)
        if not installment.is_paid:
            raise InstallmentNotPaidError()
        ensure_payment_date_is_not_in_the_future(payment_date, today)
        installment.payment_date = payment_date
        self._session.commit()
        return installment

    def reverse_payment(self, installment_id: uuid.UUID) -> Installment:
        """Estorna a baixa: a parcela volta a ficar em aberto, ou atrasada se já
        venceu (US26-CA02)."""
        installment = self._get_installment_for_update(installment_id)
        if not installment.is_paid:
            raise InstallmentNotPaidError()
        installment.payment_date = None
        self._session.commit()
        return installment

    def update(
        self, installment_id: uuid.UUID, request: InstallmentUpdateRequest
    ) -> Sequence[Installment]:
        """Edits one installment before its payment (US17-CA03) and returns the
        whole plan, since a new amount also changes the following installments."""
        installment = self._get_installment_for_update(installment_id)
        ensure_agreement_is_not_cancelled(installment)
        if installment.is_paid:
            raise PaidInstallmentCannotBeEditedError()

        plan = self._installments.list_by_agreement(installment.agreement_id)
        if request.amount is not None and request.amount != installment.amount:
            self._change_amount(installment, request.amount, plan)
        if request.due_date is not None:
            installment.due_date = request.due_date
        self._session.commit()
        return plan

    def _change_amount(
        self,
        installment: Installment,
        new_amount: Decimal,
        plan: Sequence[Installment],
    ) -> None:
        """The following open installments absorb the difference (US17-CA03), and
        the fee still to be received is split again among the open installments, so
        each keeps condominium part + fee part = amount (US16-CA02)."""
        agreement = self._agreements.get(installment.agreement_id)
        assert agreement is not None  # the installment's foreign key guarantees it
        following_open = [
            other
            for other in plan
            if other.number > installment.number and not other.is_paid
        ]
        if not following_open:
            raise NoOpenInstallmentAfterError()
        following_amounts = absorb_difference(
            new_amount - installment.amount,
            [other.amount for other in following_open],
        )
        new_amounts = {installment.id: new_amount}
        for other, amount in zip(following_open, following_amounts, strict=True):
            new_amounts[other.id] = amount

        open_installments = [item for item in plan if not item.is_paid]
        open_amounts = [
            new_amounts.get(item.id, item.amount) for item in open_installments
        ]
        fee_already_paid = sum(
            (item.fee_amount for item in plan if item.is_paid), Decimal(0)
        )
        open_fees = split_fee(open_amounts, agreement.fee_amount - fee_already_paid)
        for item, amount, fee in zip(
            open_installments, open_amounts, open_fees, strict=True
        ):
            item.amount = amount
            item.fee_amount = fee
            item.condominium_amount = amount - fee

    def _get_installment_for_update(self, installment_id: uuid.UUID) -> Installment:
        """Parcela a ser alterada. A linha fica travada até o commit, para uma baixa
        e uma edição simultâneas não deixarem uma parcela paga editada (US17-CA03)."""
        installment = self._installments.get_for_update(installment_id)
        if installment is None:
            raise InstallmentNotFoundError()
        return installment


def ensure_agreement_is_not_cancelled(installment: Installment) -> None:
    """Um acordo cancelado não recebe baixa nem edição de parcela (US20). A correção
    e o estorno de uma baixa continuam permitidos ao Administrador: sem reativação,
    são o único jeito de consertar um pagamento lançado por engano."""
    if installment.agreement.status == AgreementStatus.CANCELLED:
        raise AgreementCancelledError()


def ensure_payment_date_is_not_in_the_future(payment_date: date, today: date) -> None:
    """A baixa registra um pagamento que já aconteceu; antes do vencimento pode."""
    if payment_date > today:
        raise PaymentDateInTheFutureError()
