import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.orm import Session

from advocondo.acordos.errors import AgreementNotFoundError
from advocondo.acordos.repository import AgreementRepository
from advocondo.parcelas.errors import (
    InstallmentNotFoundError,
    NoOpenInstallmentAfterError,
    PaidInstallmentCannotBeEditedError,
)
from advocondo.parcelas.models import Installment
from advocondo.parcelas.plan import absorb_difference, split_fee
from advocondo.parcelas.repository import InstallmentRepository
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

    def update(
        self, installment_id: uuid.UUID, request: InstallmentUpdateRequest
    ) -> Sequence[Installment]:
        """Edits one installment before its payment (US17-CA03) and returns the
        whole plan, since a new amount also changes the following installments."""
        installment = self._installments.get(installment_id)
        if installment is None:
            raise InstallmentNotFoundError()
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
