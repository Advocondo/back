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
from advocondo.parcelas.plan import absorb_difference
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
        following_open = [
            other
            for other in plan
            if other.number > installment.number and not other.is_paid
        ]
        if not following_open:
            raise NoOpenInstallmentAfterError()
        new_following_amounts = absorb_difference(
            new_amount - installment.amount,
            [other.amount for other in following_open],
        )
        installment.amount = new_amount
        for other, amount in zip(following_open, new_following_amounts, strict=True):
            other.amount = amount
