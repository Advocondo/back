import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Final, Literal

from sqlalchemy.orm import Session

from advocondo.acordos.errors import AgreementCancelledError, AgreementNotFoundError
from advocondo.acordos.models import AgreementEditField
from advocondo.acordos.repository import AgreementRepository
from advocondo.common.clock import Clock
from advocondo.parcelas.errors import (
    InstallmentAlreadyPaidError,
    InstallmentNotFoundError,
    InstallmentNotPaidError,
    InvoiceDateInTheFutureError,
    NoOpenInstallmentAfterError,
    PaidInstallmentCannotBeEditedError,
    PartiallyPaidInstallmentCannotBeEditedError,
    PaymentAboveRemainingAmountError,
    PaymentDateInTheFutureError,
)
from advocondo.parcelas.models import (
    Installment,
    InstallmentChange,
    InstallmentChangeLog,
    InstallmentPayment,
)
from advocondo.parcelas.plan import (
    absorb_difference,
    first_and_last_day_of_month,
    split_fee,
)
from advocondo.parcelas.repository import InstallmentFilters, InstallmentRepository
from advocondo.parcelas.schemas import InstallmentUpdateRequest, InvoiceRequest
from advocondo.users.models import User

# Alteração do acordo (US19) que entra no histórico financeiro junto com as das
# parcelas (US31).
AgreementEdited = Literal["agreement_edited"]
AGREEMENT_EDITED: Final[AgreementEdited] = "agreement_edited"


@dataclass(frozen=True)
class FinancialHistoryEntry:
    """Uma linha do histórico financeiro do acordo (US31-CA01)."""

    changed_at: datetime
    changed_by: User
    change: InstallmentChange | AgreementEdited
    installment_number: int | None
    field: AgreementEditField | None
    old_value: str | None
    new_value: str | None


class InstallmentService:
    def __init__(
        self,
        session: Session,
        installments: InstallmentRepository,
        agreements: AgreementRepository,
        clock: Clock,
    ) -> None:
        self._session = session
        self._installments = installments
        self._agreements = agreements
        self._clock = clock

    def list_plan(self, agreement_id: uuid.UUID) -> Sequence[Installment]:
        """The installments of an agreement, in order."""
        if self._agreements.get(agreement_id) is None:
            raise AgreementNotFoundError()
        return self._installments.list_by_agreement(agreement_id)

    def financial_history(self, agreement_id: uuid.UUID) -> list[FinancialHistoryEntry]:
        """Baixas, correções, estornos e edições das parcelas do acordo, junto com as
        alterações do próprio acordo (US19), da mais recente para a mais antiga."""
        if self._agreements.get(agreement_id) is None:
            raise AgreementNotFoundError()
        installment_entries = [
            FinancialHistoryEntry(
                changed_at=log.changed_at,
                changed_by=log.changed_by,
                change=log.change,
                installment_number=number,
                field=None,
                old_value=log.old_value,
                new_value=log.new_value,
            )
            for log, number in self._installments.list_change_logs_of_agreement(
                agreement_id
            )
        ]
        agreement_entries = [
            FinancialHistoryEntry(
                changed_at=log.edited_at,
                changed_by=log.edited_by,
                change=AGREEMENT_EDITED,
                installment_number=None,
                field=log.field,
                old_value=log.old_value,
                new_value=log.new_value,
            )
            for log in self._agreements.list_edit_logs(agreement_id)
        ]
        return sorted(
            [*installment_entries, *agreement_entries],
            key=lambda entry: entry.changed_at,
            reverse=True,
        )

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
        self,
        installment_id: uuid.UUID,
        payment_date: date,
        amount: Decimal | None,
        today: date,
        recorded_by: User,
    ) -> Installment:
        """Registra um pagamento da parcela em aberto. Sem valor, ele quita o saldo e
        a parcela passa a constar como paga (US26-CA01); com um valor menor, o saldo
        restante continua em aberto (US28-CA01)."""
        installment = self._get_installment_for_update(installment_id)
        ensure_agreement_is_not_cancelled(installment)
        if installment.is_paid:
            raise InstallmentAlreadyPaidError()
        ensure_payment_date_is_not_in_the_future(payment_date, today)
        paid_now = installment.remaining_amount if amount is None else amount
        if paid_now > installment.remaining_amount:
            raise PaymentAboveRemainingAmountError()
        installment.receive(paid_now, payment_date)
        self._log(
            installment,
            recorded_by,
            InstallmentChange.PAYMENT_RECORDED,
            None,
            money_text(paid_now),
        )
        self._session.commit()
        return installment

    def get(self, installment_id: uuid.UUID) -> Installment:
        """Uma parcela, com o acordo, o condomínio e o devedor (#89-CA01)."""
        installment = self._installments.get(installment_id)
        if installment is None:
            raise InstallmentNotFoundError()
        return installment

    def list_payments(self, installment_id: uuid.UUID) -> Sequence[InstallmentPayment]:
        """Pagamentos da parcela, na ordem em que foram registrados (US28-CA02)."""
        installment = self._installments.get(installment_id)
        if installment is None:
            raise InstallmentNotFoundError()
        return installment.payments

    def correct_payment(
        self,
        installment_id: uuid.UUID,
        payment_date: date,
        today: date,
        corrected_by: User,
    ) -> Installment:
        """Troca a data do pagamento de uma parcela já baixada (US26-CA02)."""
        installment = self._get_installment_for_update(installment_id)
        if not installment.is_paid:
            raise InstallmentNotPaidError()
        ensure_payment_date_is_not_in_the_future(payment_date, today)
        previous_date = installment.payment_date
        if payment_date != previous_date:
            installment.correct_payment_date(payment_date)
            self._log(
                installment,
                corrected_by,
                InstallmentChange.PAYMENT_CORRECTED,
                date_text(previous_date),
                date_text(payment_date),
            )
        self._session.commit()
        return installment

    def reverse_payment(
        self, installment_id: uuid.UUID, reversed_by: User
    ) -> Installment:
        """Estorna os pagamentos, inclusive os parciais: a parcela volta a ficar em
        aberto, ou atrasada se já venceu (US26-CA02)."""
        installment = self._get_installment_for_update(installment_id)
        if not installment.has_payments:
            raise InstallmentNotPaidError()
        reversed_amount = installment.paid_amount
        installment.reverse_payments()
        self._log(
            installment,
            reversed_by,
            InstallmentChange.PAYMENT_REVERSED,
            money_text(reversed_amount),
            None,
        )
        self._session.commit()
        return installment

    def register_invoice(
        self, installment_id: uuid.UUID, request: InvoiceRequest, today: date
    ) -> Installment:
        """Vincula a nota fiscal à parcela paga (US29-CA01). Registrar de novo troca
        a nota, para corrigir um número ou uma data digitados errado."""
        installment = self._get_installment_for_update(installment_id)
        if not installment.is_paid:
            raise InstallmentNotPaidError()
        if request.issue_date > today:
            raise InvoiceDateInTheFutureError()
        installment.invoice_number = request.number
        installment.invoice_date = request.issue_date
        self._session.commit()
        return installment

    def list_paid_without_invoice(
        self, limit: int, offset: int
    ) -> Sequence[Installment]:
        """Parcelas pagas que ainda não têm nota fiscal (US29-CA02)."""
        return self._installments.search_paid_without_invoice(limit, offset)

    def update(
        self,
        installment_id: uuid.UUID,
        request: InstallmentUpdateRequest,
        edited_by: User,
    ) -> Sequence[Installment]:
        """Edits one installment before its payment (US17-CA03) and returns the
        whole plan, since a new amount also changes the following installments."""
        installment = self._get_installment_for_update(installment_id)
        ensure_agreement_is_not_cancelled(installment)
        if installment.is_paid:
            raise PaidInstallmentCannotBeEditedError()
        # O novo valor poderia ficar abaixo do que já foi pago (US28).
        if installment.has_payments:
            raise PartiallyPaidInstallmentCannotBeEditedError()

        plan = self._installments.list_by_agreement(installment.agreement_id)
        if request.amount is not None and request.amount != installment.amount:
            previous_amount = installment.amount
            self._change_amount(installment, request.amount, plan)
            self._log(
                installment,
                edited_by,
                InstallmentChange.AMOUNT_EDITED,
                money_text(previous_amount),
                money_text(request.amount),
            )
        if request.due_date is not None and request.due_date != installment.due_date:
            self._log(
                installment,
                edited_by,
                InstallmentChange.DUE_DATE_EDITED,
                date_text(installment.due_date),
                date_text(request.due_date),
            )
            installment.due_date = request.due_date
        self._session.commit()
        return plan

    def _change_amount(
        self,
        installment: Installment,
        new_amount: Decimal,
        plan: Sequence[Installment],
    ) -> None:
        """The following installments without payments absorb the difference
        (US17-CA03, US28), and the fee still to be received is split again among the
        open installments, so each keeps condominium part + fee part = amount
        (US16-CA02)."""
        agreement = self._agreements.get(installment.agreement_id)
        assert agreement is not None  # the installment's foreign key guarantees it
        # Parcelas com pagamento parcial também não absorvem a diferença: o valor delas
        # poderia ficar abaixo do que já foi pago (US28).
        following_open = [
            other
            for other in plan
            if other.number > installment.number and not other.has_payments
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

    def _log(
        self,
        installment: Installment,
        changed_by: User,
        change: InstallmentChange,
        old_value: str | None,
        new_value: str | None,
    ) -> None:
        """Registra a movimentação na mesma transação da mudança (US31-CA01)."""
        self._session.add(
            InstallmentChangeLog(
                installment_id=installment.id,
                changed_by_id=changed_by.id,
                changed_at=self._clock.now(),
                change=change,
                old_value=old_value,
                new_value=new_value,
            )
        )

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
    if installment.agreement.is_cancelled:
        raise AgreementCancelledError()


def ensure_payment_date_is_not_in_the_future(payment_date: date, today: date) -> None:
    """A baixa registra um pagamento que já aconteceu; antes do vencimento pode."""
    if payment_date > today:
        raise PaymentDateInTheFutureError()


def money_text(amount: Decimal) -> str:
    return f"{amount:.2f}"


def date_text(value: date | None) -> str | None:
    return None if value is None else value.isoformat()
