import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from advocondo.acordos.errors import (
    AgreementAlreadyCancelledError,
    AgreementCancelledError,
    AgreementNotCancelledError,
    AgreementNotFoundError,
    DebtorFromAnotherCondominiumError,
    FeeAboveTotalError,
    OpenInstallmentsNotConfirmedError,
    PaidInstallmentsNeedConfirmationError,
)
from advocondo.acordos.fees import fee_from_percentage
from advocondo.acordos.models import Agreement, AgreementEditField, AgreementEditLog
from advocondo.acordos.renegotiation import (
    fee_after_edit,
    recalculate_open_installments,
)
from advocondo.acordos.repository import AgreementFilters, AgreementRepository
from advocondo.acordos.schemas import (
    AgreementCancelRequest,
    AgreementCreateRequest,
    AgreementUpdateRequest,
)
from advocondo.common.clock import Clock
from advocondo.condominios.errors import CondominiumNotFoundError
from advocondo.condominios.repository import CondominiumRepository
from advocondo.devedores.errors import DebtorNotFoundError
from advocondo.devedores.models import Debtor
from advocondo.devedores.repository import DebtorRepository
from advocondo.notificacoes.models import ClientNotificationEvent
from advocondo.notificacoes.service import ClientNotificationService
from advocondo.parcelas.models import Installment
from advocondo.parcelas.plan import monthly_due_dates, split_amount, split_fee
from advocondo.users.models import User


class AgreementService:
    def __init__(
        self,
        session: Session,
        agreements: AgreementRepository,
        condominiums: CondominiumRepository,
        debtors: DebtorRepository,
        clock: Clock,
        notifications: ClientNotificationService,
    ) -> None:
        self._session = session
        self._agreements = agreements
        self._condominiums = condominiums
        self._debtors = debtors
        self._clock = clock
        self._notifications = notifications

    def register(self, request: AgreementCreateRequest, closed_by: User) -> Agreement:
        """Registers an agreement of a debtor with their condominium (US15)."""
        condominium = self._condominiums.get(request.condominium_id)
        if condominium is None:
            raise CondominiumNotFoundError()
        debtor = self._debtors.get(request.debtor_id)
        if debtor is None:
            raise DebtorNotFoundError()
        if debtor.condominium_id != condominium.id:
            raise DebtorFromAnotherCondominiumError()

        fee = fee_in_reais(request)
        agreement = Agreement(
            condominium=condominium,
            debtor=debtor,
            closed_by_id=closed_by.id,
            total_amount=request.total_amount,
            fee_amount=fee,
            fee_percentage=request.fee_percentage,
            installments=build_installments(request, fee),
        )
        self._agreements.save(agreement)
        self._session.commit()
        self._notify_client(
            agreement,
            ClientNotificationEvent.AGREEMENT_CREATED,
            "Um novo acordo foi registrado para este condomínio.",
        )
        return agreement

    def cancel(
        self, agreement_id: uuid.UUID, request: AgreementCancelRequest
    ) -> Agreement:
        """Cancela o acordo (US20). As parcelas sem pagamento são guardadas, mas
        saem da cobrança; se houver alguma, o usuário precisa confirmar."""
        # Travado para dois cancelamentos simultâneos não se sobrescreverem.
        agreement = self._agreements.get_for_update(agreement_id)
        if agreement is None:
            raise AgreementNotFoundError()
        if agreement.is_cancelled:
            raise AgreementAlreadyCancelledError()

        unpaid = agreement.unpaid_installments
        if unpaid and not request.confirm_open_installments:
            raise OpenInstallmentsNotConfirmedError(
                len(unpaid), sum((item.amount for item in unpaid), Decimal(0))
            )

        agreement.cancel(request.reason, self._clock.now())
        self._agreements.save(agreement)
        self._session.commit()
        self._notify_client(
            agreement,
            ClientNotificationEvent.AGREEMENT_CANCELLED,
            "Um acordo deste condomínio foi cancelado.",
        )
        return agreement

    def reactivate(self, agreement_id: uuid.UUID) -> Agreement:
        """Reativa um acordo cancelado (#88). As parcelas sem pagamento voltam à
        cobrança como estão: as que venceram no período cancelado ficam atrasadas."""
        # Travado como no cancelamento, para não cruzar com um cancelamento.
        agreement = self._agreements.get_for_update(agreement_id)
        if agreement is None:
            raise AgreementNotFoundError()
        if not agreement.is_cancelled:
            raise AgreementNotCancelledError()

        agreement.reactivate()
        self._agreements.save(agreement)
        self._session.commit()
        return agreement

    def get(self, agreement_id: uuid.UUID) -> Agreement:
        agreement = self._agreements.get(agreement_id)
        if agreement is None:
            raise AgreementNotFoundError()
        return agreement

    def update(
        self, agreement_id: uuid.UUID, request: AgreementUpdateRequest, edited_by: User
    ) -> Agreement:
        """Corrige ou renegocia um acordo e guarda quem alterou e quando (US19)."""
        agreement = self.get(agreement_id)
        if agreement.is_cancelled:
            raise AgreementCancelledError()
        debtor = self._new_debtor(agreement, request)
        new_total = (
            agreement.total_amount
            if request.total_amount is None
            else request.total_amount
        )
        fee = fee_after_edit(
            new_total,
            request.fee_percentage,
            request.fee_amount,
            agreement.fee_percentage,
            agreement.fee_amount,
        )
        money_changed = (
            new_total != agreement.total_amount or fee.amount != agreement.fee_amount
        )
        if debtor is None and not money_changed:
            return agreement
        client_relevant_change = (
            debtor is not None or new_total != agreement.total_amount
        )

        paid = [item for item in agreement.installments if item.is_paid]
        open_installments = [
            item for item in agreement.installments if not item.is_paid
        ]
        new_values = (
            recalculate_open_installments(
                new_total,
                fee.amount,
                sum((item.amount for item in paid), Decimal(0)),
                sum((item.fee_amount for item in paid), Decimal(0)),
                len(open_installments),
            )
            if money_changed
            else []
        )
        if paid and not request.confirm_paid_installments:
            raise PaidInstallmentsNeedConfirmationError()

        edited_at = self._clock.now()
        logs: list[AgreementEditLog] = []
        if debtor is not None:
            logs.append(
                edit_log(
                    agreement,
                    edited_by,
                    edited_at,
                    AgreementEditField.DEBTOR,
                    describe_debtor(agreement.debtor),
                    describe_debtor(debtor),
                )
            )
            agreement.debtor = debtor
        if new_total != agreement.total_amount:
            logs.append(
                edit_log(
                    agreement,
                    edited_by,
                    edited_at,
                    AgreementEditField.TOTAL_AMOUNT,
                    f"{agreement.total_amount:.2f}",
                    f"{new_total:.2f}",
                )
            )
            agreement.total_amount = new_total
        if fee.amount != agreement.fee_amount:
            logs.append(
                edit_log(
                    agreement,
                    edited_by,
                    edited_at,
                    AgreementEditField.FEE_AMOUNT,
                    f"{agreement.fee_amount:.2f}",
                    f"{fee.amount:.2f}",
                )
            )
            agreement.fee_amount = fee.amount
        agreement.fee_percentage = fee.percentage
        # Sem mudança de valor, new_values é vazio e as parcelas ficam como estão.
        for installment, values in zip(open_installments, new_values, strict=False):
            installment.amount = values.amount
            installment.fee_amount = values.fee_amount
            installment.condominium_amount = values.amount - values.fee_amount

        self._session.add_all(logs)
        self._session.commit()
        if client_relevant_change:
            self._notify_client(
                agreement,
                ClientNotificationEvent.AGREEMENT_UPDATED,
                "As informações de um acordo deste condomínio foram atualizadas.",
            )
        return agreement

    def _notify_client(
        self,
        agreement: Agreement,
        event_type: ClientNotificationEvent,
        message: str,
    ) -> None:
        self._notifications.send_condominium_update(
            agreement.condominium_id, event_type, message
        )

    def _new_debtor(
        self, agreement: Agreement, request: AgreementUpdateRequest
    ) -> Debtor | None:
        """Devedor novo, ou None quando o devedor não muda."""
        if request.debtor_id is None or request.debtor_id == agreement.debtor_id:
            return None
        debtor = self._debtors.get(request.debtor_id)
        if debtor is None:
            raise DebtorNotFoundError()
        if debtor.condominium_id != agreement.condominium_id:
            raise DebtorFromAnotherCondominiumError()
        return debtor

    def search(
        self, filters: AgreementFilters, limit: int, offset: int
    ) -> Sequence[Agreement]:
        return self._agreements.search(filters, limit, offset)


def fee_in_reais(request: AgreementCreateRequest) -> Decimal:
    """The fee typed in reais, or calculated from the percentage (US16-CA01)."""
    if request.fee_amount is not None:
        fee = request.fee_amount
    else:
        assert request.fee_percentage is not None  # ensured by the request schema
        fee = fee_from_percentage(request.total_amount, request.fee_percentage)
    if fee > request.total_amount:
        raise FeeAboveTotalError()
    return fee


def build_installments(
    request: AgreementCreateRequest, fee: Decimal
) -> list[Installment]:
    """Monthly installments that add up to the total amount (US17-CA01, CA02),
    each split between the condominium and the office (US16-CA01, CA02)."""
    amounts = split_amount(request.total_amount, request.installment_count)
    fees = split_fee(amounts, fee)
    due_dates = monthly_due_dates(request.first_due_date, request.installment_count)
    return [
        Installment(
            number=number,
            due_date=due_date,
            amount=amount,
            condominium_amount=amount - installment_fee,
            fee_amount=installment_fee,
        )
        for number, (due_date, amount, installment_fee) in enumerate(
            zip(due_dates, amounts, fees, strict=True), start=1
        )
    ]


def describe_debtor(debtor: Debtor) -> str:
    return f"{debtor.name} ({debtor.unit})"


def edit_log(
    agreement: Agreement,
    edited_by: User,
    edited_at: datetime,
    field: AgreementEditField,
    old_value: str,
    new_value: str,
) -> AgreementEditLog:
    return AgreementEditLog(
        agreement_id=agreement.id,
        edited_by_id=edited_by.id,
        edited_at=edited_at,
        field=field,
        old_value=old_value,
        new_value=new_value,
        had_paid_installments=any(item.is_paid for item in agreement.installments),
    )
